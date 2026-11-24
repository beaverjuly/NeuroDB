#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m neurodb.acquire "$@"
.venv/bin/python -m neurodb.transform
.venv/bin/python -m neurodb.ingest
.venv/bin/python -m neurodb.check_idempotence
.venv/bin/python -m neurodb.validate
.venv/bin/python -m neurodb.benchmark
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build_notebook.py
.venv/bin/jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=300 notebooks/NeuroDB_Demo.ipynb
.venv/bin/python scripts/finalize_demo.py
