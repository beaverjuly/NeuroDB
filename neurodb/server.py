"""Dedicated socket-only MySQL 8.4 instance, separate from existing servers."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
import pymysql
from . import ROOT

RUNTIME = ROOT / '.runtime'
_short_socket_dir = Path(tempfile.gettempdir()) / ('ndb-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12])
SOCKET = RUNTIME / 'mysql.sock' if len(str(RUNTIME / 'mysql.sock').encode()) < 90 else _short_socket_dir / 'mysql.sock'

def connect(admin=False, database=True, readonly=False):
    user = 'root' if admin else ('neurodb_reader' if readonly else 'neurodb_demo')
    return pymysql.connect(unix_socket=str(SOCKET), user=user,
        database='neurodb' if database else None, charset='utf8mb4', autocommit=True,
        cursorclass=pymysql.cursors.DictCursor)


def ensure_reader():
    """Keep ad hoc SQL on a separate account with no write privileges."""
    with connect(admin=True, database=False) as conn, conn.cursor() as cursor:
        cursor.execute("CREATE USER IF NOT EXISTS 'neurodb_reader'@'localhost' IDENTIFIED BY ''")
        cursor.execute("REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'neurodb_reader'@'localhost'")
        cursor.execute("GRANT SELECT, SHOW VIEW ON neurodb.* TO 'neurodb_reader'@'localhost'")

def start():
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    RUNTIME.chmod(0o700)
    SOCKET.parent.mkdir(mode=0o700, exist_ok=True)
    SOCKET.parent.chmod(0o700)
    try:
        with connect(admin=True, database=False) as conn, conn.cursor() as c:
            c.execute('SELECT VERSION() AS version')
            version=c.fetchone()['version']
            if not version.startswith('8.4.'):
                raise RuntimeError('Expected MySQL 8.4, found '+version)
            print('MySQL '+version+' ready', flush=True)
            return
    except pymysql.err.OperationalError:
        pass
    base=Path(os.environ.get('NEURODB_MYSQL_HOME','/usr/local/mysql'))
    binary=base/'bin/mysqld'
    version=subprocess.check_output([str(binary),'--no-defaults','--version'],text=True)
    if '8.4.' not in version:
        raise RuntimeError('Set NEURODB_MYSQL_HOME to a MySQL 8.4 installation')
    data=RUNTIME/'mysql-data'
    if not data.exists():
        subprocess.run([str(binary),'--no-defaults','--initialize-insecure',
            '--basedir='+str(base),'--datadir='+str(data)],check=True,capture_output=True)
    log=RUNTIME/'mysql.log'
    with log.open('ab') as out:
        subprocess.Popen([str(binary),'--no-defaults','--basedir='+str(base),
            '--datadir='+str(data),'--socket='+str(SOCKET),'--pid-file='+str(RUNTIME/'mysql.pid'),
            '--skip-networking','--mysqlx=OFF','--log-error='+str(log),
            '--innodb-buffer-pool-size=128M'],stdout=out,stderr=out,start_new_session=True)
    # A cold InnoDB restart on a laptop can take longer than 20 seconds.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with connect(admin=True,database=False) as conn, conn.cursor() as c:
                c.execute('SELECT VERSION() AS version')
                print('MySQL '+c.fetchone()['version']+' ready',flush=True)
                return
        except pymysql.err.OperationalError:
            time.sleep(.2)
    raise RuntimeError('MySQL did not start. Inspect '+str(log))

def stop():
    with connect(admin=True,database=False) as conn, conn.cursor() as c:
        c.execute('SHUTDOWN')

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop'])
    args=p.parse_args()
    start() if args.action=='start' else stop()
