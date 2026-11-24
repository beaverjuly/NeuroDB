"""Local, dependency-light browser interface over the validated MySQL workload."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import pymysql
from urllib.parse import urlsplit

from . import ROOT
from .custom_sql import run_custom_sql
from .queries import QUERIES
from .server import connect, ensure_reader, start

HOST = '127.0.0.1'
PORT = 8765
PAGE = ROOT / 'web/index.html'
DIAGRAMS = ROOT / 'web/diagrams'
DIAGRAM_SOURCE = ROOT / 'docs/NeuroDB_Query_Logic_Diagrams.pdf'


def fetch(sql, params=()):
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def overview():
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT VERSION() AS version')
        version = cursor.fetchone()['version']
        counts = {}
        for table in ('participants', 'runs', 'trials', 'events', 'latent_values'):
            cursor.execute(f'SELECT COUNT(*) AS total FROM {table}')
            counts[table] = cursor.fetchone()['total']
        cursor.execute('SELECT COUNT(*) AS total FROM ingestion_runs WHERE status=%s', ('passed',))
        loads = cursor.fetchone()['total']
    return {'mysql_version': version, 'counts': counts, 'successful_loads': loads,
            'validation': json.loads((ROOT / 'results/validation.json').read_text())['passed']}


def catalog():
    return {'queries': {key: {'title': item.title, 'question': item.question, 'note': item.note,
                               'sql': item.sql} for key, item in QUERIES.items()},
            'participants': fetch("SELECT bids_label FROM participants WHERE inclusion_status='validated' ORDER BY bids_label"),
            'runs': fetch("SELECT p.bids_label,r.run_id,r.run_number FROM participants p JOIN sessions s USING(participant_id) JOIN runs r USING(session_id) WHERE r.run_type='functional' ORDER BY p.bids_label,r.run_number")}


def performance():
    data = json.loads((ROOT / 'results/benchmark.json').read_text())
    event = {window: {name: {'median_ms': round(value['median_ms'], 3),
                              'handler_reads': value['median_handler_reads'],
                              'returned_rows': value['returned_rows'],
                              'selectivity': value['within_run_selectivity'],
                              'plan': value['explain_analyze']}
                      for name, value in designs.items()}
             for window, designs in data['event_experiments'].items()}
    wide = {name: {'median_ms': round(value['median_ms'], 3),
                   'handler_reads': value['median_handler_reads'],
                   'returned_rows': value['returned_rows'],
                   'plan': value['explain_analyze']}
            for name, value in data['extensibility'].items()}
    return {'measured_at': data['measured_at'], 'event': event, 'wide': wide,
            'wide_refresh_ms': round(data['wide_refresh_ms'], 1),
            'wide_physical_storage': data['wide_physical_storage'],
            'repeats': data['repeats'], 'warmup_runs': data['warmup_runs']}


def run_query(body):
    qid = body.get('qid')
    if qid not in QUERIES:
        raise ValueError('Choose a listed question')
    participant = body.get('participant') or None
    if participant is not None and not isinstance(participant, str):
        raise ValueError('Invalid participant')
    condition = body.get('condition')
    if condition not in (None, 1, 2):
        raise ValueError('Reward condition must be 1, 2, or all')
    run_id = int(body.get('run_id') or 0)
    start_time = float(body.get('start', 0))
    end_time = float(body.get('end', 60))
    if not 0 <= start_time < end_time <= 10000:
        raise ValueError('Use a window with 0 ≤ start < end ≤ 10000 seconds')
    if qid in ('Q3', 'Q8'):
        if run_id <= 0:
            raise ValueError('Choose a functional run')
        owner = fetch('SELECT p.bids_label FROM runs r JOIN sessions s USING(session_id) JOIN participants p USING(participant_id) WHERE r.run_id=%s AND r.run_type=%s', (run_id, 'functional'))
        if not owner or (participant and owner[0]['bids_label'] != participant):
            raise ValueError('The selected run does not belong to this participant')
    variable = body.get('variable') or 'spe_planet'
    if variable not in ('spe_planet', 'mf_value_chosen', 'mb_value_chosen', 'mf_rpe_outcome', 'mb_rpe_outcome'):
        raise ValueError('Choose a listed model variable')
    params = {'participant': participant, 'condition': condition, 'run_id': run_id,
              'start': start_time, 'end': end_time, 'variable': variable}
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(QUERIES[qid].sql, params)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        if body.get('show_plan') is True:
            cursor.execute('EXPLAIN ANALYZE ' + QUERIES[qid].sql, params)
            plan = str(next(iter(cursor.fetchone().values())))
        else:
            plan = None
    result = {'columns': columns, 'rows': rows, 'count': len(rows),
              'question': QUERIES[qid].question, 'note': QUERIES[qid].note}
    if plan is not None:
        result['plan'] = plan
    return result


class Handler(BaseHTTPRequestHandler):
    def send(self, value, status=200, content_type='application/json; charset=utf-8'):
        payload = value if isinstance(value, bytes) else json.dumps(value, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        route = urlsplit(self.path).path
        try:
            if route == '/':
                return self.send(PAGE.read_bytes(), content_type='text/html; charset=utf-8')
            if route.startswith('/diagrams/'):
                filename = route.removeprefix('/diagrams/')
                if filename in {f'Q{index}.png' for index in range(1, 9)}:
                    return self.send((DIAGRAMS / filename).read_bytes(), content_type='image/png')
                return self.send({'error': 'Page not found'}, status=404)
            if route == '/query-diagrams':
                return self.send(DIAGRAM_SOURCE.read_bytes(), content_type='application/pdf')
            if route == '/api/overview':
                return self.send(overview())
            if route == '/api/catalog':
                return self.send(catalog())
            if route == '/api/performance':
                return self.send(performance())
            if route == '/walkthrough':
                return self.send((ROOT / 'results/NeuroDB_Demo.html').read_bytes(), content_type='text/html; charset=utf-8')
            if route == '/health':
                return self.send({'ok': True})
            return self.send({'error': 'Page not found'}, status=404)
        except Exception as exc:
            return self.send({'error': str(exc)}, status=500)

    def do_POST(self):
        route = urlsplit(self.path).path
        if route not in ('/api/query', '/api/custom-query'):
            return self.send({'error': 'Page not found'}, status=404)
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= (16384 if route == '/api/custom-query' else 4096):
            return self.send({'error': 'Invalid request size'}, status=400)
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected a query object')
            if route == '/api/custom-query':
                return self.send(run_custom_sql(body.get('sql')))
            return self.send(run_query(body))
        except (ValueError, TypeError, pymysql.err.MySQLError) as exc:
            return self.send({'error': str(exc)}, status=400)
        except Exception as exc:
            return self.send({'error': str(exc)}, status=500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    start()
    ensure_reader()
    server = ThreadingHTTPServer((HOST, args.port), Handler)
    pid_file = ROOT / '.runtime/webapp.pid'
    pid_file.write_text(str(os.getpid()))
    print(f'NeuroDB Explorer is ready at http://{HOST}:{args.port}/', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if pid_file.exists() and pid_file.read_text().strip() == str(os.getpid()):
            pid_file.unlink()


if __name__ == '__main__':
    main()
