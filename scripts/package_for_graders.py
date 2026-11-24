"""Create a self-contained, bounded grading ZIP with one named root folder."""
from datetime import datetime
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neurodb import ROOT
from neurodb.acquire import digest

DESTINATION = Path.home() / 'Downloads' / 'NeuroDB_DSCI551_Grader_Package.zip'
DIRECTORIES = ['neurodb', 'scripts', 'sql', 'notebooks', 'docs', 'database', 'data/raw', 'data/derived', 'tests', 'web', 'results/presentation']
ROOT_FILES = ['GRADERS_START_HERE.md', 'README.md', 'Launch NeuroDB.command', 'Launch NeuroDB Explorer.command', 'Stop NeuroDB.command', 'requirements.txt', 'requirements.lock.txt']
RESULT_FILES = ['NeuroDB_Demo.html', 'RESULTS.md', 'benchmark.json', 'benchmark_summary.tsv',
                'validation.json', 'idempotence.json', 'tests.log', 'stay_behavior.png',
                'index_selectivity.png', 'schema_overview.png']

def collect():
    paths = [ROOT / name for name in ROOT_FILES]
    for name in DIRECTORIES:
        paths.extend(p for p in (ROOT / name).rglob('*') if p.is_file())
    paths.extend(ROOT / 'results' / name for name in RESULT_FILES)
    paths.extend(p for p in (ROOT / 'results').glob('Q[1-8].tsv'))
    paths = sorted(set(paths))
    forbidden = {'.venv', '.runtime', '.git', '__pycache__', '.pytest_cache', '.ipynb_checkpoints'}
    paths = [p for p in paths if not forbidden.intersection(p.parts) and p.name != '.DS_Store']
    if any(not p.exists() for p in paths):
        raise FileNotFoundError([str(p) for p in paths if not p.exists()])
    proposal = ROOT.parent / 'NeuroDB_Revised_Proposal.pdf'
    if not proposal.is_file():
        raise FileNotFoundError(proposal)
    return paths, proposal

def main():
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true', help='Use the saved passing database audit and verify pinned source checksums without starting MySQL')
    args = parser.parse_args()
    if args.offline:
        report = json.loads((ROOT / 'results/validation.json').read_text())
    else:
        from neurodb.validate import validate
        report = validate(save=False)
    if not report['passed']:
        raise RuntimeError('Database validation is not passing')
    if not json.loads((ROOT / 'results/idempotence.json').read_text())['passed']:
        raise RuntimeError('Idempotence validation is not passing')
    dump = ROOT / 'database/neurodb.sql'
    if 'Dump completed' not in dump.read_text()[-300:]:
        raise RuntimeError('MySQL dump is incomplete')
    paths, proposal = collect()
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir='/tmp', prefix='.NeuroDB-package-', suffix='.zip', delete=False) as handle:
        temporary = Path(handle.name)
    entries = {}
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            with ThreadPoolExecutor(max_workers=64) as pool:
              for path, payload in zip(paths + [proposal], pool.map(Path.read_bytes, paths + [proposal])):
                name = 'NeuroDB/' + (str(path.relative_to(ROOT)) if path != proposal else 'docs/NeuroDB_Revised_Proposal.pdf')
                if name in entries:
                    raise RuntimeError('Duplicate archive entry ' + name)
                entries[name] = hashlib.sha256(payload).hexdigest()
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, payload)
            listing = '\n'.join(f'{sha}  {name.removeprefix("NeuroDB/")}' for name, sha in entries.items()) + '\n'
            archive.writestr('NeuroDB/PACKAGE_MANIFEST.sha256', listing)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('Archive CRC validation failed')
            members = set(archive.namelist())
            if members != set(entries) | {'NeuroDB/PACKAGE_MANIFEST.sha256'}:
                raise RuntimeError('Archive entry mismatch')
            for name, sha in entries.items():
                if hashlib.sha256(archive.read(name)).hexdigest() != sha:
                    raise RuntimeError('Archive checksum mismatch for ' + name)
        temporary.replace(DESTINATION)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'{DESTINATION}\n{len(entries) + 1} files, {DESTINATION.stat().st_size:,} bytes')
    print('SHA256 ' + digest(DESTINATION))

if __name__ == '__main__':
    main()
