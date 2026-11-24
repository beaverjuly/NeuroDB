#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."
neurodb_python="${NEURODB_PYTHON:-python3.11}"
neurodb_mysql_home="${NEURODB_MYSQL_HOME:-/usr/local/mysql}"
if [[ ! -x "$neurodb_mysql_home/bin/mysqld" || ! -x "$neurodb_mysql_home/bin/mysql" ]]; then
    print -u2 "MySQL 8.4 was not found at $neurodb_mysql_home. Set NEURODB_MYSQL_HOME to its installation directory."
    exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
    "$neurodb_python" -m venv .venv
    .venv/bin/python -m pip install -r requirements.lock.txt
fi
.venv/bin/python -m ipykernel install --prefix .venv --name neurodb --display-name NeuroDB
.venv/bin/python -m neurodb.server start
.venv/bin/python -c 'from neurodb.ingest import initialize; initialize()'
neurodb_socket="$(.venv/bin/python -c 'from neurodb.server import SOCKET; print(SOCKET)')"
"$neurodb_mysql_home/bin/mysql" --no-defaults --socket="$neurodb_socket" -u root < database/neurodb.sql
.venv/bin/python -m neurodb.validate
print "NeuroDB is ready. Open Launch NeuroDB.command or run .venv/bin/jupyter lab notebooks/NeuroDB_Demo.ipynb"
