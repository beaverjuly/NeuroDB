"""On-demand physical-design measurements using disposable MySQL tables."""

from datetime import datetime, timezone
import math
import time

from .measurement import compare
from .server import connect

EVENT_COLUMNS = ('event_id,run_id,trial_id,event_type_id,event_sequence,'
                 'onset_seconds,duration_seconds,source_timestamp,source_field,source_file_id')
EVENT_DESIGNS = ('baseline', 'composite', 'covering', 'reversed')
WINDOW_WIDTHS = (10, 60, 300, 720)


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a number')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a number') from exc
    if not math.isfinite(result):
        raise ValueError(f'{label} must be finite')
    return result


def _settings(body):
    kind = body.get('experiment')
    if kind not in ('index', 'selectivity', 'materialization'):
        raise ValueError('Choose an experiment type')
    repeats = body.get('repeats', 3)
    if type(repeats) is not int or repeats not in (3, 5, 9):
        raise ValueError('Choose 3, 5, or 9 timed repetitions')
    settings = {'experiment': kind, 'repeats': repeats}
    if kind == 'materialization':
        return settings
    run_id = body.get('run_id')
    if type(run_id) is not int or run_id <= 0:
        raise ValueError('Choose a functional run')
    start = _number(body.get('start', 0), 'Start time')
    if not 0 <= start < 10000:
        raise ValueError('Start time must be between 0 and 10000 seconds')
    settings.update(run_id=run_id, start=start)
    if kind == 'index':
        end = _number(body.get('end', 60), 'End time')
        if not start < end <= 10000:
            raise ValueError('Use 0 ≤ start < end ≤ 10000 seconds')
        settings['end'] = end
    else:
        widths = body.get('widths', list(WINDOW_WIDTHS))
        if not isinstance(widths, list) or len(widths) < 2 or len(widths) > len(WINDOW_WIDTHS):
            raise ValueError('Select at least two window widths')
        if any(type(width) is not int or width not in WINDOW_WIDTHS for width in widths) or len(set(widths)) != len(widths):
            raise ValueError('Choose distinct widths from 10, 60, 300, and 720 seconds')
        if start + max(widths) > 10000:
            raise ValueError('The largest window must end by 10000 seconds')
        settings['widths'] = sorted(widths)
    return settings


def _event_table(cursor, design):
    table = 'live_events_' + design
    cursor.execute(f'CREATE TEMPORARY TABLE {table} LIKE events')
    if design != 'composite':
        cursor.execute(f'ALTER TABLE {table} DROP INDEX idx_events_run_onset')
    if design == 'covering':
        cursor.execute(f'ALTER TABLE {table} ADD INDEX idx_cover(run_id,onset_seconds,event_id,trial_id,event_type_id,duration_seconds)')
    if design == 'reversed':
        cursor.execute(f'ALTER TABLE {table} ADD INDEX idx_reversed(onset_seconds,run_id)')
    cursor.execute(f'INSERT INTO {table} ({EVENT_COLUMNS}) SELECT {EVENT_COLUMNS} FROM events ORDER BY event_id')
    cursor.execute(f'ANALYZE TABLE {table}')
    cursor.fetchall()


def _event_sql(design):
    return ('SELECT event_id,run_id,trial_id,event_type_id,onset_seconds,duration_seconds '
            f'FROM live_events_{design} WHERE run_id=%s AND onset_seconds >= %s '
            'AND onset_seconds < %s ORDER BY onset_seconds,event_id')


def _rows(details, window_seconds=None, run_count=None):
    rows = []
    for design, detail in details.items():
        count = detail['returned_rows']
        rows.append({
            'design': design,
            'window_seconds': window_seconds,
            'median_ms': round(detail['median_ms'], 4),
            'handler_reads': detail['median_handler_reads'],
            'returned_rows': count,
            'selectivity': count / run_count if run_count else None,
            'sql': detail['sql'],
            'params': detail['params'],
            'plan': detail['explain_analyze'],
            'samples': [{'milliseconds': round(sample['milliseconds'], 4),
                         'handler_reads': sample['handler_reads']}
                        for sample in detail['samples']],
            'result_sha256': detail['samples'][0]['result_sha256'],
        })
    return rows


def run_live_experiment(body):
    """Run one bounded experiment without changing canonical tables or saved results."""
    settings = _settings(body)
    kind = settings['experiment']
    started = time.perf_counter()
    result = {
        'experiment': kind,
        'measured_at': datetime.now(timezone.utc).isoformat(),
        'repeats': settings['repeats'],
        'warmup_runs': 2,
        'timing_scope': 'client execute plus fetch over local MySQL socket',
        'counter_scope': 'session Handler read operations, not physical disk reads',
        'table_scope': 'session-local temporary copies; canonical tables and saved benchmarks unchanged',
    }
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT VERSION() AS version')
        result['mysql_version'] = cursor.fetchone()['version']
        if kind in ('index', 'selectivity'):
            cursor.execute('''SELECT r.run_id,r.run_number,r.run_duration,p.bids_label
                FROM runs r JOIN sessions s USING(session_id)
                JOIN participants p USING(participant_id)
                WHERE r.run_id=%s AND r.run_type='functional' ''', (settings['run_id'],))
            run = cursor.fetchone()
            if run is None:
                raise ValueError('Choose a functional run')
            result['run'] = {**run, 'run_duration': float(run['run_duration']) if run['run_duration'] is not None else None}
            cursor.execute('SELECT COUNT(*) AS n FROM events WHERE run_id=%s', (settings['run_id'],))
            run_count = cursor.fetchone()['n']
            if not run_count:
                raise ValueError('The selected run has no events')
            result['run_event_count'] = run_count
            cursor.execute('SELECT COUNT(*) AS n FROM events')
            result['source_event_count'] = cursor.fetchone()['n']
            designs = EVENT_DESIGNS if kind == 'index' else ('baseline', 'composite')
            setup_started = time.perf_counter()
            for design in designs:
                _event_table(cursor, design)
            result['setup_ms'] = round((time.perf_counter() - setup_started) * 1000, 2)
            cases = {design: _event_sql(design) for design in designs}
            if kind == 'index':
                params = (settings['run_id'], settings['start'], settings['end'])
                details = compare(cursor, cases, params, settings['repeats'])
                result['interval'] = {'start': settings['start'], 'end': settings['end']}
                result['rows'] = _rows(details, settings['end'] - settings['start'], run_count)
            else:
                result['start'] = settings['start']
                result['widths'] = settings['widths']
                result['rows'] = []
                for width in settings['widths']:
                    details = compare(cursor, cases,
                                      (settings['run_id'], settings['start'], settings['start'] + width),
                                      settings['repeats'])
                    result['rows'].extend(_rows(details, width, run_count))
        else:
            refresh_started = time.perf_counter()
            cursor.execute('CREATE TEMPORARY TABLE live_trial_wide AS SELECT * FROM trial_context')
            cursor.execute('ALTER TABLE live_trial_wide ADD PRIMARY KEY(trial_id), ADD INDEX idx_wide_run(run_type,participant_id,reward_condition)')
            result['refresh_ms'] = round((time.perf_counter() - refresh_started) * 1000, 2)
            cursor.execute('ANALYZE TABLE live_trial_wide')
            cursor.fetchall()
            cursor.execute('SELECT COUNT(*) AS n FROM live_trial_wide')
            result['wide_rows'] = cursor.fetchone()['n']
            aggregation = '''SELECT participant_id,reward_condition,COUNT(*) AS n,SUM(reward) AS rewards
                FROM {table} WHERE run_type='functional' AND response_valid=1
                GROUP BY participant_id,reward_condition ORDER BY participant_id,reward_condition'''
            cases = {'normalized': aggregation.format(table='trial_context'),
                     'materialized': aggregation.format(table='live_trial_wide')}
            details = compare(cursor, cases, (), settings['repeats'])
            result['rows'] = _rows(details)
    result['total_ms'] = round((time.perf_counter() - started) * 1000, 2)
    result['identical_results'] = True
    return result
