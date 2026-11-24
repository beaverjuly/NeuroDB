"""Shared query timing and result-equality checks for physical-design experiments."""

import hashlib
import json
import random
import statistics
import time


def counters(cursor):
    cursor.execute("SHOW SESSION STATUS LIKE 'Handler_read%'")
    return {row['Variable_name']: int(row['Value']) for row in cursor.fetchall()}


def run_once(cursor, sql, params):
    before = counters(cursor)
    started = time.perf_counter_ns()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    elapsed = (time.perf_counter_ns() - started) / 1e6
    after = counters(cursor)
    delta = {key: after[key] - value for key, value in before.items()}
    checksum = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    return {'milliseconds': elapsed, 'handler_reads': sum(delta.values()),
            'handler_counters': delta, 'returned_rows': len(rows),
            'result_sha256': checksum}


def compare(cursor, cases, params, repeats=9):
    details = {}
    for label, sql in cases.items():
        for _ in range(2):
            cursor.execute(sql, params)
            cursor.fetchall()
        cursor.execute('EXPLAIN ANALYZE ' + sql, params)
        plan = '\n'.join(next(iter(row.values())) for row in cursor.fetchall())
        cursor.execute('EXPLAIN FORMAT=JSON ' + sql, params)
        estimated = json.loads(next(iter(cursor.fetchone().values())))
        details[label] = {'sql': sql, 'params': params, 'explain_analyze': plan,
                          'estimated_plan': estimated, 'samples': []}
    rng = random.Random(551)
    for _ in range(repeats):
        order = list(cases)
        rng.shuffle(order)
        for label in order:
            details[label]['samples'].append(run_once(cursor, cases[label], params))
    hashes = {sample['result_sha256'] for detail in details.values() for sample in detail['samples']}
    if len(hashes) != 1:
        raise AssertionError('Compared access paths returned different results')
    for detail in details.values():
        detail['median_ms'] = statistics.median(sample['milliseconds'] for sample in detail['samples'])
        detail['median_handler_reads'] = statistics.median(sample['handler_reads'] for sample in detail['samples'])
        detail['returned_rows'] = detail['samples'][0]['returned_rows']
    return details
