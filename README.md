# NeuroDB

A working MySQL 8.4 and Jupyter demonstration for Julia (Jiahe) Yi's individual DSCI 551 project. Public two step task observations are normalized into a reusable core, a task detail extension and a validated pilot model extension.

## Open the demo

For the simplest live interface, double click **Launch NeuroDB Explorer.command**. It opens a local browser page with five sections: overview, predefined queries, custom SQL, index experiments, and sources. Q1 through Q8 show only relevant filters, clear stale results when inputs change, and place results above the parameterized SQL and bound values. The matching query logic diagram from `docs/NeuroDB_Query_Logic_Diagrams.pdf` appears beside the query on wide screens and can be enlarged. The Custom SQL section accepts one read only statement, offers prepared examples and an execution plan action, and shows at most 200 rows. It uses a separate read only account and a five second query limit. The interface runs against the same MySQL database as the notebook. It uses Python's built-in web server, with no additional web framework dependency, and listens only on `127.0.0.1`.

When finished, double click **Stop NeuroDB.command** to stop the explorer, JupyterLab and the private MySQL instance.

For the detailed, executed teaching notebook, use the original launcher below. The two interfaces can run at the same time.

Double click **Launch NeuroDB.command**, then use **Run → Run All Cells** in the notebook. The launcher starts this project's dedicated MySQL instance and opens JupyterLab. MySQL uses a private local socket inside `.runtime`. Existing MySQL installations and databases are not modified.

The primary artifact is [notebooks/NeuroDB_Demo.ipynb](notebooks/NeuroDB_Demo.ipynb). Keep the small [SQL Playground notebook](notebooks/SQL_Playground.ipynb) open in a second JupyterLab tab for unexpected questions. Its `query()` alias uses the same bounded read only path as the explorer. The saved [HTML walkthrough](results/NeuroDB_Demo.html) can be opened without starting MySQL, but its saved outputs are not live queries.

The notebook embeds presentation figures beside the matching discussion. Three ERD panels cover all 19 entities and show primary keys, foreign keys, selected attributes and cardinality. Other figures explain one observed trial, the run crosswalk, event integrity, index plans, materialization and validation. Q1, Q3 and Q8 diagrams appear in the standalone explorer. All presentation figures are available as PNGs under `results/presentation/`. The complete keyed ERD with every attribute is in `docs/schema.mmd`, generated from `sql/schema.sql` by `python3 scripts/build_schema_mermaid.py`. Regenerate presentation figures from saved results with `python3 scripts/build_presentation_visuals.py`, then embed the selected notebook figures with `python3 scripts/add_presentation_visuals.py`. For the six minute presentation, switch to the separate browser explorer only for live Q1 and Q3.

```sh
cd NeuroDB
./'Launch NeuroDB.command'
```

For the shareable grading ZIP, start with [GRADERS_START_HERE.md](GRADERS_START_HERE.md). It includes a database dump and a setup route that does not need MATLAB.

## GitHub source copy

This repository contains the source code, schema, executed notebooks, browser interface, source manifest, figures and saved query and benchmark results. The public OSF downloads, derived timing audits with local filesystem paths and MySQL dump are kept in the separate grading ZIP. You can review [the saved walkthrough](results/NeuroDB_Demo.html) without running MySQL. The live explorer requires a populated database, which the grading ZIP can restore with `scripts/prepare_grader_demo.sh`.

To rebuild from public source files instead, use the pinned [source manifest](data/raw/manifest.json) with `python -m neurodb.acquire` and follow the full rebuild steps below. Rebuilding event timing requires MATLAB and the validated pilot model artifacts described in [docs/SOURCES.md](docs/SOURCES.md).

Use [the speaking guide](docs/DEMO_GUIDE.md) for a suggested classroom sequence. The explorer offers all eight proposed queries. The notebook saves outputs for the selected demonstrations, with Q5 and Q6 clearly restricted to the validated pilot.

## What is implemented

| Proposal commitment | Implementation |
| --- | --- |
| MySQL 8.4 | Dedicated MySQL 8.4.11 instance, InnoDB, constraints and natural keys |
| Real data and provenance | OSF file versions, SHA256 checksums, OpenNeuro 1.0.5 identity inventory |
| Reproducible ingestion | Frozen downloads, strict MATLAB export, transactional upserts and audit records |
| Generic and task-specific schema | 19 tables and the `trial_context` view |
| Meaningful workload | Q1 through Q8 with parameterized SQL and explicit missingness rules |
| Event indexing | Existing indexes compared with composite, covering and reversed alternatives |
| Selectivity | 10, 60, 300 and 720 second windows over the same functional run |
| Extensibility cost | Generic joins compared with an equivalent materialized wide copy |
| Performance evidence | Actual and estimated plans, warm medians, result equality and Handler counters |
| Interactive application | Participant, run, reward condition and time filters, results, SQL and plans |
| Verification | Source checks, independent Q1 calculation, relationship checks and integration tests |

Current exact counts and pass/fail results are in [results/validation.json](results/validation.json). Participant inclusion in this database is separate from inclusion in the paper's analytic sample. The imported model quantities cover one validated pilot only.

## Reproduce

The current environment is already installed in `.venv`. It uses the local MySQL installation at `/usr/local/mysql` and MATLAB R2025b. Only the rebuild requires MATLAB. Set `NEURODB_MYSQL_HOME` or `NEURODB_MATLAB` to use another compatible installation.

For a fresh environment with Python 3.11

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m ipykernel install --prefix .venv --name neurodb --display-name NeuroDB
```

The full rebuild checks the frozen input files, decodes MATLAB tables, loads MySQL, validates, benchmarks and executes the notebook

```sh
./scripts/rebuild.sh --offline
```

Omit `--offline` to download any missing OSF inputs from the pinned manifest. Acquisition stops on an HTTP 429 response and preserves completed downloads. Retry later if OSF rate limits a request. It never regenerates the manifest automatically after it exists.

On a fresh checkout, the validated pilot extension requires the original reproduction project beside the DSCI551 folder or the already verified files under `data/raw/pilot`. This dependency is intentional and documented; the code never fabricates pilot latents. The existing local package contains those files.

To rerun only the load and validation

```sh
.venv/bin/python -m neurodb.ingest
.venv/bin/python -m neurodb.validate
.venv/bin/python -m pytest -q
```

Reloading preserves the scientific rows and creates a new ingestion audit. The loader refuses changed source bytes at an already loaded path, preventing silent mixing of snapshots. The database instance can be stopped after class

```sh
.venv/bin/python -m neurodb.server stop
```

## Evidence and limits

The event experiment uses isolated temporary copies, so baseline indexes can be changed without disabling canonical foreign keys. Each alternative must return the same result checksum. Physical wide-table allocation is measured from a matching copy in the separate `neurodb_benchmark` database and that copy is removed afterward. JSON size is reported separately as a logical payload measure. Small warm timings should be interpreted together with plan operators and Handler counters.

The raw observations are attributed to the study authors and distributed by OSF under the license recorded in [data/raw/osf_license.json](data/raw/osf_license.json). Data-derived tables and figures retain that source attribution. Author code and fit attribution are recorded separately in [docs/SOURCES.md](docs/SOURCES.md). The full grading ZIP is distributed separately from this repository.
