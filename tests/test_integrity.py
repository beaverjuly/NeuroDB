"""Integration tests target mistakes the schema and scientific queries must reject."""
import json
import pandas as pd
import pymysql
import pytest
from neurodb import ROOT
from neurodb.acquire import pair_sources
from neurodb.ingest import validate_behavior
from neurodb.server import connect
from neurodb.queries import execute,defaults
from neurodb.validate import validate

def test_all_database_validation_checks():
    report=validate(save=False)
    assert report['passed'],report['checks']

def test_crosswalk_uses_timing_identity_not_behavior_suffix():
    sources=[dict(kind='behavior',filename='sub0049s2f3.csv',path='behavior.csv'),
             dict(kind='timing',filename='subID_0049_sesID_1_MBMF_fMRI.mat',path='timing.mat')]
    pair=pair_sources(sources,{'sub-MBMF004901'})[0]
    assert pair['order']==1 and pair['bids_present']

def test_event_cannot_reference_trial_in_another_run():
    with connect(admin=True) as conn,conn.cursor() as c:
        c.execute('SELECT run_id,MIN(trial_id) AS trial_id FROM trials GROUP BY run_id ORDER BY run_id LIMIT 2')
        a,b=c.fetchall()
        c.execute('SELECT source_file_id FROM source_files LIMIT 1');source=c.fetchone()['source_file_id']
        conn.begin()
        try:
            with pytest.raises(pymysql.err.IntegrityError):
                c.execute("INSERT INTO events(run_id,trial_id,event_type_id,event_sequence,onset_seconds,duration_seconds,source_timestamp,source_field,source_file_id) VALUES(%s,%s,1,99,0,0,0,'test',%s)",(a['run_id'],b['trial_id'],source))
        finally:conn.rollback()

def test_null_trial_run_events_still_have_unique_natural_keys():
    with connect(admin=True) as conn,conn.cursor() as c:
        c.execute('SELECT run_id,source_file_id FROM runs LIMIT 1');r=c.fetchone()
        conn.begin()
        try:
            statement="INSERT INTO events(run_id,trial_id,event_type_id,event_sequence,onset_seconds,duration_seconds,source_timestamp,source_field,source_file_id) VALUES(%s,NULL,1,99,0,0,0,'test',%s)"
            c.execute(statement,(r['run_id'],r['source_file_id']))
            with pytest.raises(pymysql.err.IntegrityError):c.execute(statement,(r['run_id'],r['source_file_id']))
        finally:conn.rollback()

def test_reject_reordered_behavior_trials():
    df=pd.read_csv(ROOT/'data/raw/Control_structural_functional_behavior_csv/sub0015s2f3.csv')
    with pytest.raises(ValueError,match='Unordered'):
        validate_behavior(df.iloc[[1,0]+list(range(2,len(df)))])

def test_half_open_window_and_parameterized_participant():
    p=defaults();rows=execute('Q3',p)
    assert ((rows.onset_seconds>=p['start'])&(rows.onset_seconds<p['end'])).all()
    p['participant']="' OR 1=1 --"
    assert execute('Q7',p).empty
    p['end']=p['start']
    with pytest.raises(ValueError):execute('Q3',p)

def test_benchmark_results_identical_across_physical_designs():
    path=ROOT/'results/benchmark.json'
    if not path.exists():pytest.skip('Run python -m neurodb.benchmark first')
    results=json.loads(path.read_text())
    for comparison in list(results['event_experiments'].values())+[results['extensibility']]:
        assert len({s['result_sha256'] for d in comparison.values() for s in d['samples']})==1
