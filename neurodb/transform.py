"""Run the existing strict MATLAB decoder against each pinned participant pair."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import pandas as pd
from . import ROOT, TRANSFORM_VERSION
from .acquire import digest

def main():
    p=argparse.ArgumentParser();p.add_argument('--reuse',action='store_true');args=p.parse_args()
    manifest=json.loads((ROOT/'data/raw/manifest.json').read_text())
    out=ROOT/'data/derived';out.mkdir(exist_ok=True)
    fingerprints={str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'scripts/events').glob('*.m'))}
    fingerprints['neurodb/transform.py']=digest(ROOT/'neurodb/transform.py')
    configs=[];unavailable=[]
    for person in manifest['participants']:
        if not person['timing'] or not person['bids_present']:
            unavailable.append(dict(bids_label=person['bids_label'],passed=False,reason='No matched BIDS identity or timing source'))
            continue
        if any(not (ROOT/person[kind]).exists() for kind in ('behavior','timing')):
            unavailable.append(dict(bids_label=person['bids_label'],passed=False,reason='Source not downloaded; acquisition incomplete'))
            continue
        label=person['bids_label'];folder=out/label;folder.mkdir(exist_ok=True)
        sources={}
        for kind in ('behavior','timing'):
            source=next(s for s in manifest['sources'] if s['path']==person[kind])
            if digest(ROOT/source['path'])!=source['sha256']:
                raise ValueError('Checksum mismatch '+source['path'])
            sources[kind]={'path':source['path'],'sha256':source['sha256']}
        behavior=pd.read_csv(ROOT/person['behavior'])
        functional_runs=behavior.loc[behavior.sess_type=='functional','runID'].drop_duplicates().tolist()
        if len(functional_runs)!=2:raise ValueError('Expected two functional runs for '+label)
        config=dict(schema_version=TRANSFORM_VERSION,
            participant=dict(timing_subject_id=person['person'],timing_session_id=person['order'],openneuro_id=label),
            sources=sources,
            run_mapping=[dict(timing_run_id=i,behavior_run_id=int(br),
                first_functional_trial_id=(i-1)*77+1,last_functional_trial_id=i*77) for i,br in enumerate(functional_runs,1)])
        config_path=folder/'config.json';config_path.write_text(json.dumps(config,indent=2))
        configs.append(dict(label=label,config=str(config_path),output=str(folder)))
    stamp={'source_manifest':digest(ROOT/'data/raw/manifest.json'),'exporter_files':fingerprints,'available':[x['label'] for x in configs],
           'transform_version':TRANSFORM_VERSION}
    old=out/'transform_stamp.json'
    if args.reuse and old.exists() and json.loads(old.read_text())==stamp:
        print('Reusing verified transformation snapshot');return
    (out/'batch.json').write_text(json.dumps(configs))
    matlab=Path(os.environ.get('NEURODB_MATLAB','/Applications/MATLAB_R2025b.app/bin/matlab'))
    command="addpath('"+str(ROOT/'scripts/events').replace("'","''")+"'); export_cohort('"+str(ROOT).replace("'","''")+"');"
    subprocess.run([str(matlab),'-batch',command],check=True,cwd=ROOT)
    status=out/'cohort_validation.json'
    status.write_text(json.dumps(json.loads(status.read_text())+unavailable,indent=2))
    old.write_text(json.dumps(stamp,indent=2))

if __name__=='__main__':main()
