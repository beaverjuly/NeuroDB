"""Frozen, checksummed public sources. No voxel downloads or inferred records."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import time
import urllib.request
import urllib.error
from . import ROOT

RAW = ROOT / 'data/raw'
REPRO = ROOT.parents[1] / 'ds007474-modelbasedfMRI-reproduction'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'NeuroDB-course-demo/1.0'})
            with urllib.request.urlopen(req, timeout=45) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError('OSF rate limit reached. Retry acquisition later; existing files are preserved.') from exc
            if attempt == 3:raise
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

def listing(url):
    result = []
    while url:
        page = json.loads(get(url))
        result.extend(page['data'])
        url = page['links']['next']
    return result

def pair_sources(sources,bids):
    pairs=[]
    for f in sources:
        if f['kind']!='behavior':continue
        m=re.fullmatch(r'sub(\d{4})s([23])f([23])\.csv',f['filename'])
        if not m:raise ValueError('Unrecognized behavioral identity '+f['filename'])
        person=m[1]
        candidates=[s for s in sources if re.fullmatch(r'subID_'+person+r'_sesID_[12]_MBMF_fMRI\.mat',s['filename'])]
        if len(candidates)!=1:raise ValueError('Timing identity is missing or ambiguous for '+person)
        timing=candidates[0]
        order=int(re.fullmatch(r'subID_\d{4}_sesID_([12])_MBMF_fMRI\.mat',timing['filename'])[1])
        label=f'sub-MBMF{person}{order:02d}'
        pairs.append(dict(bids_label=label,person=person,order=order,behavior=f['path'],timing=timing['path'],bids_present=label in bids))
    return sorted(pairs,key=lambda x:x['bids_label'])

def inventory():
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / 'manifest.json'
    if path.exists():
        return json.loads(path.read_text())
    node = json.loads(get('https://api.osf.io/v2/nodes/ctfzd/'))
    (RAW / 'osf_project.json').write_text(json.dumps(node, indent=2))
    license_url=node['data']['relationships']['license']['links']['related']['href']
    license_record=json.loads(get(license_url))
    (RAW/'osf_license.json').write_text(json.dumps(license_record,indent=2))
    tree = json.loads(get('https://api.github.com/repos/OpenNeuroDatasets/ds007474/git/trees/1.0.5'))
    (RAW / 'openneuro_tree.json').write_text(json.dumps(tree, indent=2))
    (RAW / 'openneuro_README.md').write_bytes(get('https://raw.githubusercontent.com/OpenNeuroDatasets/ds007474/1.0.5/README'))
    bids = {x['path'] for x in tree['tree'] if x['path'].startswith('sub-')}
    sources = []
    for folder in listing('https://api.osf.io/v2/nodes/ctfzd/files/osfstorage/?page[size]=100'):
        name = folder['attributes']['name']
        if name not in ('Control_structural_functional_behavior_csv', 'Control_functional_behavior_event_timing_mat'):
            continue
        entries = listing(folder['relationships']['files']['links']['related']['href']+'?page[size]=100')
        for f in entries:
            a = f['attributes']
            sha = a['extra']['hashes']['sha256']
            if not sha:
                raise ValueError('No upstream checksum for '+a['name'])
            sources.append(dict(kind='behavior' if name.endswith('csv') else 'timing',
                filename=a['name'], path='data/raw/'+name+'/'+a['name'],
                url=f['links']['download']+'?version='+str(a['current_version']),
                sha256=sha, snapshot='OSF file '+f['id']+' version '+str(a['current_version']),
                license_status=license_record['data']['attributes']['name']))
    pairs=pair_sources(sources,bids)
    result = dict(acquired_at=datetime.now(timezone.utc).isoformat(),
                  openneuro_version='1.0.5', openneuro_tree=tree['sha'],
                  sources=sources, participants=sorted(pairs, key=lambda x:x['bids_label']))
    path.write_text(json.dumps(result, indent=2))
    return result

def fetch_one(source, offline=False):
    destination = ROOT / source['path']
    if not destination.exists():
        if offline:
            raise FileNotFoundError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        old = REPRO / 'sourcedata/osf' / destination.parent.name / destination.name
        if old.exists() and digest(old) == source['sha256']:
            shutil.copyfile(old, destination)
        else:
            payload = get(source['url'])
            if hashlib.sha256(payload).hexdigest() != source['sha256']:
                raise ValueError('Downloaded checksum mismatch '+source['filename'])
            destination.write_bytes(payload)
    if digest(destination) != source['sha256']:
        raise ValueError('Local checksum mismatch '+source['filename'])
    return source['filename']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if args.offline and not (RAW / 'manifest.json').exists():
        raise FileNotFoundError('Offline mode needs data/raw/manifest.json')
    manifest = inventory()
    for i,s in enumerate(manifest['sources'],1):
        missing=not (ROOT/s['path']).exists()
        fetch_one(s,args.offline)
        if missing:time.sleep(.5)
        if i%20==0 or i==len(manifest['sources']):
            print(f"Verified {i}/{len(manifest['sources'])} source files",flush=True)
    print(f"Frozen inventory contains {len(manifest['participants'])} participant pairs", flush=True)

if __name__ == '__main__':
    main()
