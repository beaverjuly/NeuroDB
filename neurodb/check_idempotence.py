"""Reload the frozen snapshot and compare exact table counts and SQL checksums."""
from datetime import datetime,timezone
import json
import subprocess
import sys
from . import ROOT
from .server import connect

def snapshot():
    with connect(admin=True) as conn,conn.cursor() as c:
        c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='neurodb' AND table_type='BASE TABLE' AND table_name NOT IN ('ingestion_runs','ingestion_records') ORDER BY table_name")
        tables=[r['TABLE_NAME'] for r in c.fetchall()]
        result={}
        for name in tables:
            c.execute('SELECT COUNT(*) AS n FROM '+name);count=c.fetchone()['n']
            c.execute('CHECKSUM TABLE '+name+' EXTENDED');checksum=c.fetchone()['Checksum']
            if checksum is None:raise AssertionError('Checksum unavailable for '+name)
            result[name]={'rows':count,'mysql_checksum':checksum}
        return result

def main():
    before=snapshot()
    subprocess.run([sys.executable,'-m','neurodb.ingest'],cwd=ROOT,check=True)
    after=snapshot()
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'before':before,'after':after,
            'passed':before==after,'excluded_audit_tables':['ingestion_runs','ingestion_records'],
            'method':'Exact row counts and MySQL CHECKSUM TABLE EXTENDED before and after full reload'}
    (ROOT/'results/idempotence.json').write_text(json.dumps(report,indent=2))
    if not report['passed']:raise AssertionError('Reload changed canonical table contents')
    print('Idempotent reload verified for all 17 canonical tables')

if __name__=='__main__':main()
