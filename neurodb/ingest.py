"""Validated, transactional and idempotent loading of frozen observations."""
import hashlib
import json
import math
import shutil
import subprocess
import pandas as pd
from . import ROOT, TRANSFORM_VERSION
from .acquire import digest, REPRO
from .server import connect, ensure_reader, start

EVENTS=['fixation','stimulus','response_left','response_right','response_missing','planet','pad','outcome']
EVENT_IDS={name:i+1 for i,name in enumerate(EVENTS)}

def clean(value):
    if value is None or pd.isna(value): return None
    if hasattr(value,'item'): value=value.item()
    if isinstance(value,float) and not math.isfinite(value): raise ValueError('Infinite input')
    return value

def upsert(c,table,row):
    columns=list(row)
    sql=f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))}) ON DUPLICATE KEY UPDATE "+','.join(f'{k}=VALUES({k})' for k in columns)
    c.execute(sql,tuple(clean(row[k]) for k in columns))

def bulk(c,table,columns,rows):
    if not rows:return
    sql=f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))}) ON DUPLICATE KEY UPDATE "+','.join(f'{k}=VALUES({k})' for k in columns)
    c.executemany(sql,[tuple(clean(v) for v in row) for row in rows])

def one(c,sql,args=()):
    c.execute(sql,args);return next(iter(c.fetchone().values()))

def source(c,path,url,snapshot,license_status):
    path=ROOT/path if not hasattr(path,'read_bytes') else path
    sha=digest(path)
    rel=str(path.relative_to(ROOT))
    # A different snapshot must not silently mix old facts and new input.
    c.execute('SELECT checksum FROM source_files WHERE local_path=%s',(rel,))
    if any(r['checksum']!=sha for r in c.fetchall()):
        raise ValueError('Source changed after loading; use a new database snapshot '+rel)
    upsert(c,'source_files',dict(local_path=rel,source_url=url,snapshot=snapshot,checksum=sha,license_status=license_status))
    return one(c,'SELECT source_file_id FROM source_files WHERE local_path=%s AND checksum=%s',(rel,sha))

def initialize():
    start()
    with connect(admin=True,database=False) as conn,conn.cursor() as c:
        for statement in (ROOT/'sql/schema.sql').read_text().split(';'):
            if statement.strip():c.execute(statement)
        c.execute("CREATE USER IF NOT EXISTS 'neurodb_demo'@'localhost' IDENTIFIED BY ''")
        c.execute("GRANT SELECT, SHOW VIEW, CREATE TEMPORARY TABLES ON neurodb.* TO 'neurodb_demo'@'localhost'")
        c.execute('CREATE DATABASE IF NOT EXISTS neurodb_benchmark')
        c.execute("GRANT SELECT, INSERT, CREATE, DROP, ALTER ON neurodb_benchmark.* TO 'neurodb_demo'@'localhost'")
        for name,eid in EVENT_IDS.items():
            rule='missed only' if name=='response_missing' else ('completed only' if name in ['planet','pad','outcome','response_left','response_right'] else 'every trial')
            upsert(c,'event_types',dict(event_type_id=eid,event_name=name,trial_status_rules=rule))
    ensure_reader()

def validate_behavior(df):
    required=['runID','sess_type','trialID','Resp1','outcome1','outcome2','outcomeBin','outcomeMag','doRareTrans','RT1','condReward','condContingent','condState']
    if set(required)-set(df):raise ValueError('Missing behavioral columns')
    if len(df)!=259:raise ValueError(f'Expected 259 behavior trials, found {len(df)}')
    if df.runID.drop_duplicates().tolist()!=[1,2,3]:raise ValueError('Unexpected behavior run coverage')
    functional_runs=df.loc[df.sess_type=='functional','runID'].drop_duplicates().tolist()
    structural_runs=df.loc[df.sess_type=='structural','runID'].drop_duplicates().tolist()
    if len(functional_runs)!=2 or len(structural_runs)!=1:raise ValueError('Unexpected session coverage')
    for run,g in df.groupby('runID',sort=False):
        if g.sess_type.nunique()!=1 or g.sess_type.iloc[0] not in ['structural','functional']:
            raise ValueError('Unexpected behavior session mapping')
        i=functional_runs.index(run) if run in functional_runs else None
        expected=list(range(1,106)) if i is None else list(range(i*77+1,(i+1)*77+1))
        if g.trialID.tolist()!=expected:raise ValueError('Unordered or repeated source trial IDs')
    if not df.Resp1.dropna().isin([1,2]).all():raise ValueError('Invalid action code')
    if not df.doRareTrans.dropna().isin([0,1]).all():raise ValueError('Invalid transition code')
    valid=df.Resp1.notna()
    if df.loc[valid,['Resp1','outcome1','outcome2','outcomeBin','outcomeMag','RT1']].isna().any().any():
        raise ValueError('Observed response lacks required outcome')
    return df

def load_participant(c,person,pid,source_ids):
    df=validate_behavior(pd.read_csv(ROOT/person['behavior']))
    folder=ROOT/'data/derived'/person['bids_label']
    ev=pd.read_csv(folder/'events_reconstructed.tsv',sep='\t')
    audit=json.loads((folder/'timing_validation.json').read_text())
    if not audit['behavior_crosscheck']['passed']:raise ValueError('Timing crosscheck did not pass')
    if ev.participant_id.nunique()!=1 or ev.participant_id.iloc[0]!=person['bids_label']:raise ValueError('Event participant mismatch')
    behavior_id=source_ids[person['behavior']];timing_id=source_ids[person['timing']]
    upsert(c,'sessions',dict(participant_id=pid,session_label='source-task-session'))
    sid=one(c,'SELECT session_id FROM sessions WHERE participant_id=%s',(pid,))
    functional_runs=df.loc[df.sess_type=='functional','runID'].drop_duplicates().tolist()
    for br,group in df.groupby('runID',sort=False):
        functional=group.sess_type.iloc[0]=='functional';run_number=functional_runs.index(br)+1 if functional else 1
        meta=next((x for x in audit['run_summary'] if x['task_run']==run_number),{}) if functional else {}
        # Scan count and TR are verified for the pilot only. No cohort imputation.
        pilot=person['bids_label']=='sub-MBMF001502' and functional
        upsert(c,'runs',dict(session_id=sid,run_type='functional' if functional else 'structural',
            run_number=run_number,behavior_run_number=br,source_run_label=f'behavior-{br}',
            repetition_time=1.12 if pilot else None,scan_count=650 if pilot else None,
            run_duration=meta.get('run_duration'),source_file_id=timing_id if functional else behavior_id))
        rid=one(c,'SELECT run_id FROM runs WHERE session_id=%s AND behavior_run_number=%s',(sid,br))
        records=[(rid,n,int(row.trialID),int(idx)+1,int(pd.notna(row.Resp1)),behavior_id)
                 for n,(idx,row) in enumerate(group.iterrows(),1)]
        bulk(c,'trials',['run_id','trial_number','source_trial_number','source_row_number','response_valid','source_file_id'],records)
        c.execute('SELECT trial_id,trial_number FROM trials WHERE run_id=%s',(rid,))
        tids={x['trial_number']:x['trial_id'] for x in c.fetchall()}
        details=[]
        for n,(_,row) in enumerate(group.iterrows(),1):
            valid=pd.notna(row.Resp1)
            # Do not treat preassigned states or outcomes on missed trials as observed.
            details.append((tids[n],row.Resp1,row.outcome1 if valid else None,
                row.outcome2 if valid else None,row.outcomeBin if valid else None,
                row.outcomeMag if valid else None,
                ('rare' if row.doRareTrans else 'common') if valid and pd.notna(row.doRareTrans) else None,
                row.condReward,row.condContingent,row.condState,row.RT1))
        bulk(c,'two_step_trial_details',['trial_id','chosen_ship','visited_planet','visited_pad','reward','reward_magnitude',
            'transition_type','reward_condition','contingency_condition','state_condition','response_time'],details)
        if functional:
            erecords=[]
            for row in ev.loc[ev.behavior_run_id==br].itertuples():
                erecords.append((rid,tids[row.trial_in_run],EVENT_IDS[row.event_type],row.event_order,
                    row.onset,row.duration,row.source_timestamp,row.source_field,timing_id))
            bulk(c,'events',['run_id','trial_id','event_type_id','event_sequence','onset_seconds','duration_seconds',
                'source_timestamp','source_field','source_file_id'],erecords)
    return len(df),len(ev)

def load_pilot(c,source_ids):
    target=ROOT/'data/raw/pilot';target.mkdir(exist_ok=True)
    old=REPRO/'derivatives/pilot/sub-MBMF001502'
    names=['computational_regressors.tsv','model_replay_diagnostics.json','artifact_manifest.tsv']
    for name in names:
        if not (target/name).exists():shutil.copyfile(old/name,target/name)
    manifest=pd.read_csv(target/'artifact_manifest.tsv',sep='\t').set_index('artifact')
    for name in names[:2]:
        if digest(target/name)!=manifest.loc[name,'sha256']:raise ValueError('Pilot artifact checksum mismatch')
    diagnostics=json.loads((target/'model_replay_diagnostics.json').read_text())
    if not diagnostics['validation']['passed'] or not diagnostics['likelihood']['log_joint_matches_saved_fit']:
        raise ValueError('Pilot replay did not pass')
    commit='53dffece52606047922027eeae59745e09566844'
    fitrel=diagnostics['inputs']['fit_file']
    if not (target/'author_fit.mat').exists():shutil.copyfile(REPRO/fitrel,target/'author_fit.mat')
    if digest(target/'author_fit.mat')!=diagnostics['inputs']['fit_sha256']:raise ValueError('Author fit checksum mismatch')
    fit_source=source(c,target/'author_fit.mat','https://github.com/Gentu-Ding/2-step-task-MBMF-fMRI-code/blob/'+commit+'/'+fitrel.split('external/author-code/')[1],commit,'Author code and fit attribution; separate from OSF license')
    latent_source=source(c,target/'computational_regressors.tsv','local-pilot://sub-MBMF001502/computational_regressors.tsv',commit,'Local deterministic replay derivative; author code attribution')
    diagnostic_source=source(c,target/'model_replay_diagnostics.json','local-pilot://sub-MBMF001502/model_replay_diagnostics.json',commit,'Local validation report')
    pid=one(c,"SELECT participant_id FROM participants WHERE bids_label='sub-MBMF001502' AND inclusion_status='validated'")
    upsert(c,'model_specifications',dict(model_id=1,model_name='MBMF WSLS arbitration magMF binMB',version=commit,code_reference='https://github.com/Gentu-Ding/2-step-task-MBMF-fMRI-code/tree/'+commit))
    upsert(c,'fitting_jobs',dict(job_id=1,model_id=1,fitting_method='released cbm_lap fit; deterministic replay',
        prior_spec=json.dumps(diagnostics['likelihood']['prior']),code_version=commit,run_status='pilot replay validated'))
    upsert(c,'participant_fits',dict(job_id=1,participant_id=pid,objective_value=diagnostics['likelihood']['replayed_log_joint_density'],objective_kind='log joint density',fit_status='author fit replay validated',source_file_id=fit_source))
    fitid=one(c,'SELECT fit_id FROM participant_fits WHERE job_id=1 AND participant_id=%s',(pid,))
    p=diagnostics['parameters']
    for name,transform,raw,applied in zip(p['names'],p['transforms'],p['raw'],p['interpretable_baseline_or_applied']):
        upsert(c,'parameter_definitions',dict(model_id=1,parameter_name=name,transform=transform,lower_bound=None,upper_bound=None,applicability='Pilot author model; applied value or baseline; see diagnostics'))
        upsert(c,'parameter_estimates',dict(fit_id=fitid,parameter_name=name,raw_value=raw,applied_value=applied))
    cols=['mf_value_chosen','mf_value_rejected','mb_value_chosen','mb_value_rejected','spe_planet','spe_pad',
          'mf_rpe_planet','mf_rpe_pad','mf_rpe_outcome','mb_rpe_planet','mb_rpe_pad','mb_rpe_outcome','w_mf_trial','w_mb_trial','p_choice']
    for vid,name in enumerate(cols,1):
        stage=next((stage for stage in ['planet','pad','outcome'] if name.endswith('_'+stage)),'stimulus')
        unit='MF utility scale' if name.startswith('mf_') else ('MB binary reward scale' if name.startswith('mb_') else 'dimensionless')
        upsert(c,'variable_definitions',dict(variable_id=vid,model_id=1,variable_name=name,stage=stage,locking_event_type_id=EVENT_IDS[stage],units=unit))
    c.execute('SELECT trial_id,behavior_run_number,trial_number,response_valid,chosen_ship,source_trial_number FROM trial_context WHERE participant_id=%s',(pid,))
    trials={(r['behavior_run_number'],r['trial_number']):r for r in c.fetchall()}
    frame=pd.read_csv(target/'computational_regressors.tsv',sep='\t')
    records=[]
    for row in frame.itertuples():
        trial=trials[(row.run_id,row.trial_in_run)]
        if row.participant_id!='sub-MBMF001502' or row.trial_id!=trial['source_trial_number'] or row.valid_response!=trial['response_valid']:
            raise ValueError('Latent trial alignment mismatch')
        if row.valid_response:
            if row.response!=trial['chosen_ship']:raise ValueError('Latent choice mismatch')
            for vid,col in enumerate(cols,1):
                v=float(getattr(row,col))
                if not math.isfinite(v):raise ValueError('Nonfinite latent on valid trial')
                records.append((fitid,trial['trial_id'],vid,v))
        elif any(pd.notna(getattr(row,col)) for col in cols):raise ValueError('Latents on missed trial')
    bulk(c,'latent_values',['fit_id','trial_id','variable_id','value'],records)
    return {fit_source:1,latent_source:len(records),diagnostic_source:1}

def main():
    initialize()
    manifest=json.loads((ROOT/'data/raw/manifest.json').read_text())
    statuses={r['bids_label']:r for r in json.loads((ROOT/'data/derived/cohort_validation.json').read_text())}
    code=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(list((ROOT/'neurodb').glob('*.py'))+list((ROOT/'sql').glob('*.sql'))+list((ROOT/'scripts/events').glob('*.m'))))).hexdigest()
    with connect(admin=True) as conn,conn.cursor() as c:
        upsert(c,'studies',dict(study_id=1,accession='ds007474',title='Two step reinforcement learning fMRI',doi='10.1016/j.celrep.2026.117454',snapshot='OpenNeuro 1.0.5'))
        c.execute('INSERT INTO ingestion_runs(transform_version,code_checksum,status) VALUES(%s,%s,%s)',(TRANSFORM_VERSION,code,'running'))
        ingestion=c.lastrowid
        try:
            license_path=ROOT/'data/raw/osf_license.json'
            license_name=json.loads(license_path.read_text())['data']['attributes']['name']
            source_ids={}
            for src in manifest['sources']:
                if (ROOT/src['path']).exists():
                    if digest(ROOT/src['path'])!=src['sha256']:raise ValueError('Pinned checksum mismatch '+src['path'])
                    source_ids[src['path']]=source(c,src['path'],src['url'],src['snapshot'],license_name)
                    c.execute('UPDATE source_files SET available_on_disk=1 WHERE source_file_id=%s',(source_ids[src['path']],))
                else:
                    upsert(c,'source_files',dict(local_path=src['path'],source_url=src['url'],snapshot=src['snapshot'],
                        checksum=src['sha256'],license_status=license_name,available_on_disk=0))
                    source_ids[src['path']]=one(c,'SELECT source_file_id FROM source_files WHERE local_path=%s AND checksum=%s',(src['path'],src['sha256']))
            metadata_source=source(c,ROOT/'data/raw/openneuro_README.md','https://raw.githubusercontent.com/OpenNeuroDatasets/ds007474/1.0.5/README','1.0.5','OpenNeuro dataset metadata')
            for person in manifest['participants']:
                status=statuses.get(person['bids_label'],{'passed':False,'reason':'No matched BIDS identity or timing source'})
                state_only=person['bids_label'] in {f'sub-MBMF{x:04d}01' for x in range(215,220)}
                row=dict(study_id=1,source_person_id=person['person'],bids_label=person['bids_label'],task_order=person['order'],
                    design_variant='state_only' if state_only else 'mixed',inclusion_status='excluded',
                    analytic_inclusion_status='unknown',exclusion_reason=status['reason'] or None,
                    metadata_note='Fieldmap coverage incomplete for run 1' if person['bids_label']=='sub-MBMF025002' else None,
                    source_file_id=metadata_source)
                upsert(c,'participants',row)
                pid=one(c,'SELECT participant_id FROM participants WHERE study_id=1 AND bids_label=%s',(person['bids_label'],))
                counts=(0,0)
                if status['passed']:
                    conn.begin()
                    try:
                        counts=load_participant(c,person,pid,source_ids)
                        c.execute("UPDATE participants SET inclusion_status='validated',exclusion_reason=NULL WHERE participant_id=%s",(pid,))
                        conn.commit()
                    except Exception as exc:
                        conn.rollback();status=dict(passed=False,reason=str(exc))
                        c.execute("UPDATE participants SET inclusion_status='excluded',exclusion_reason=%s WHERE participant_id=%s",(str(exc),pid))
                for kind,count in zip(('behavior','timing'),counts):
                    if person[kind]:upsert(c,'ingestion_records',dict(ingestion_id=ingestion,source_file_id=source_ids[person[kind]],rows_loaded=count,
                        validation_status='passed' if status['passed'] else 'excluded',message=status['reason'] or None))
                if status['passed']:
                    for name,count in [('events_reconstructed.tsv',counts[1]),('timing_validation.json',1)]:
                        sid=source(c,ROOT/'data/derived'/person['bids_label']/name,
                            'local-transform://'+person['bids_label']+'/'+name,TRANSFORM_VERSION,'Derived from OSF '+license_name)
                        upsert(c,'ingestion_records',dict(ingestion_id=ingestion,source_file_id=sid,rows_loaded=count,
                            validation_status='passed',message='MATLAB timing transform and behavior crosscheck'))
                if pid%20==0:print(f'Processed {pid} participant identities',flush=True)
            accepted=one(c,"SELECT COUNT(*) FROM participants WHERE inclusion_status='validated'")
            if accepted<30:raise ValueError(f'Only {accepted} participants validated; minimum is 30')
            conn.begin()
            for source_id,count in load_pilot(c,source_ids).items():
                upsert(c,'ingestion_records',dict(ingestion_id=ingestion,source_file_id=source_id,rows_loaded=count,validation_status='passed',message='Validated pilot extension'))
            conn.commit()
            c.execute("UPDATE ingestion_runs SET status='passed',message=%s WHERE ingestion_id=%s",(f'{accepted} participants validated',ingestion))
            print(f'Ingestion {ingestion} completed with {accepted} validated participants',flush=True)
        except Exception as exc:
            conn.rollback()
            c.execute("UPDATE ingestion_runs SET status='failed',message=%s WHERE ingestion_id=%s",(str(exc),ingestion))
            raise

if __name__=='__main__':main()
