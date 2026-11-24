"""Controlled real-data experiments in disposable session-local tables."""
from datetime import datetime, timezone
import json
import time
import uuid
import pandas as pd
from . import ROOT
from .measurement import compare
from .server import connect
from .queries import defaults

def run_experiments(save=True,repeats=9):
    params=defaults();rid=params['run_id']
    result={'measured_at':datetime.now(timezone.utc).isoformat(),'data_kind':'real observations only',
            'warmup_runs':2,'repeats':repeats,'timing_scope':'client execute plus fetch over local socket',
            'counter_scope':'session Handler API counters; not physical disk reads',
            'controlled_tables':'session-local copies; no production indexes are changed',
            'hints':'none; MySQL chooses among each copy\u0027s available indexes',
            'event_experiments':{},'indexes':{}}
    with connect() as conn,conn.cursor() as c:
        c.execute('SELECT VERSION() AS version');result['mysql_version']=c.fetchone()['version']
        c.execute('SHOW INDEX FROM events');result['indexes']['production_events']=c.fetchall()
        c.execute('SELECT COUNT(*) AS n FROM events WHERE run_id=%s',(rid,));run_count=c.fetchone()['n']
        c.execute('SELECT COUNT(*) AS n FROM events');result['event_table_rows']=c.fetchone()['n']
        columns='event_id,run_id,trial_id,event_type_id,event_sequence,onset_seconds,duration_seconds,source_timestamp,source_field,source_file_id'
        for design in ['baseline','composite','covering','reversed']:
            table='bench_events_'+design
            c.execute(f'CREATE TEMPORARY TABLE {table} LIKE events')
            if design!='composite':c.execute(f'ALTER TABLE {table} DROP INDEX idx_events_run_onset')
            if design=='covering':c.execute(f'ALTER TABLE {table} ADD INDEX idx_cover(run_id,onset_seconds,event_id,trial_id,event_type_id,duration_seconds)')
            if design=='reversed':c.execute(f'ALTER TABLE {table} ADD INDEX idx_reversed(onset_seconds,run_id)')
            c.execute(f'INSERT INTO {table} ({columns}) SELECT {columns} FROM events ORDER BY event_id')
            c.execute(f'ANALYZE TABLE {table}');c.fetchall()
            c.execute(f'SHOW INDEX FROM {table}');result['indexes'][design]=c.fetchall()
        # Constant SELECT columns make the result and requested ordering identical.
        cases={d:f'SELECT event_id,run_id,trial_id,event_type_id,onset_seconds,duration_seconds FROM bench_events_{d} WHERE run_id=%s AND onset_seconds >= %s AND onset_seconds < %s ORDER BY onset_seconds,event_id' for d in ['baseline','composite','covering','reversed']}
        for width in [10,60,300,720]:
            details=compare(c,cases,(rid,0.,float(width)),repeats)
            for d in details.values():d['within_run_selectivity']=d['returned_rows']/run_count
            result['event_experiments'][str(width)]=details
        # Materialize the exact rows used by the generic behavioral query.
        t=time.perf_counter()
        c.execute('CREATE TEMPORARY TABLE bench_trial_wide AS SELECT * FROM trial_context')
        c.execute('ALTER TABLE bench_trial_wide ADD PRIMARY KEY(trial_id), ADD INDEX idx_wide_run(run_type,participant_id,reward_condition)')
        result['wide_refresh_ms']=(time.perf_counter()-t)*1000
        c.execute('ANALYZE TABLE bench_trial_wide');c.fetchall()
        aggregation='''SELECT participant_id,reward_condition,COUNT(*) AS n,SUM(reward) AS rewards
            FROM {table} WHERE run_type='functional' AND response_valid=1
            GROUP BY participant_id,reward_condition ORDER BY participant_id,reward_condition'''
        result['extensibility']=compare(c,{label:aggregation.format(table=table) for label,table in
            [('generic_joins','trial_context'),('wide_materialized','bench_trial_wide')]},(),repeats)
        c.execute('SHOW INDEX FROM bench_trial_wide');result['indexes']['wide']=c.fetchall()
        # Measure a transparent serialized payload, not a fictional InnoDB byte estimate.
        c.execute('SELECT * FROM bench_trial_wide ORDER BY trial_id');wide=c.fetchall()
        result['wide_rows']=len(wide)
        result['wide_serialized_json_bytes']=len(json.dumps(wide,default=str).encode())
        storage_table='wide_'+uuid.uuid4().hex[:12]
        try:
            c.execute(f'CREATE TABLE neurodb_benchmark.{storage_table} LIKE bench_trial_wide')
            c.execute(f'INSERT INTO neurodb_benchmark.{storage_table} SELECT * FROM bench_trial_wide')
            c.execute(f'ANALYZE TABLE neurodb_benchmark.{storage_table}');c.fetchall()
            c.execute('SET SESSION information_schema_stats_expiry=0')
            c.execute("SELECT data_length,index_length FROM information_schema.tables WHERE table_schema='neurodb_benchmark' AND table_name=%s",(storage_table,))
            result['wide_physical_storage']=c.fetchone()
        finally:
            c.execute(f'DROP TABLE IF EXISTS neurodb_benchmark.{storage_table}')
        result['storage_note']='Physical data and index allocation measured from a same-schema wide copy in the isolated neurodb_benchmark database after ANALYZE TABLE. The copy is removed after measurement. JSON bytes are a separate logical payload measure. Physical allocation includes page slack, not just field bytes.'
        c.execute("SELECT table_name,table_rows,data_length,index_length FROM information_schema.tables WHERE table_schema='neurodb' AND table_type='BASE TABLE' ORDER BY table_name")
        result['durable_table_storage']=c.fetchall()
    if save:
        (ROOT/'results/benchmark.json').write_text(json.dumps(result,indent=2,default=str))
        summary(result).to_csv(ROOT/'results/benchmark_summary.tsv',sep='\t',index=False)
    return result

def summary(result):
    rows=[]
    for width,configs in result['event_experiments'].items():
        for name,r in configs.items():
            rows.append(dict(experiment='event window',window_seconds=int(width),design=name,
                median_ms=r['median_ms'],handler_reads=r['median_handler_reads'],returned_rows=r['returned_rows'],
                selectivity=r['within_run_selectivity']))
    for name,r in result['extensibility'].items():
        rows.append(dict(experiment='behavior aggregation',window_seconds=None,design=name,
            median_ms=r['median_ms'],handler_reads=r['median_handler_reads'],returned_rows=r['returned_rows'],selectivity=None))
    return pd.DataFrame(rows)

if __name__=='__main__':
    results=run_experiments();print(summary(results).to_string(index=False))
