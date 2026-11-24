#!/bin/zsh
set -e
cd "$(dirname "$0")"
.venv/bin/python -m neurodb.server start
mkdir -p .runtime
print $$ > .runtime/jupyter.pid
exec .venv/bin/jupyter lab notebooks/NeuroDB_Demo.ipynb --ServerApp.ip=127.0.0.1
