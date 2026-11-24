"""Create a small, executable fallback notebook for live ad hoc questions."""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]

cells = [
    nbf.v4.new_markdown_cell('''# NeuroDB SQL Playground

Use this notebook when asked a new question during the demonstration. Edit the SQL in the next cell and run that cell. Queries use a separate read only MySQL account, stop after five seconds, and show at most 200 rows. Use one statement at a time.
'''),
    nbf.v4.new_code_cell('''from pathlib import Path
import sys

ROOT = Path.cwd() if (Path.cwd() / 'neurodb').is_dir() else Path.cwd().parent
sys.path.insert(0, str(ROOT))

from neurodb.server import start, ensure_reader
from neurodb.custom_sql import dataframe as query

start()
ensure_reader()
display(query('SELECT CURRENT_USER() AS sql_user, DATABASE() AS database_name'))'''),
    nbf.v4.new_code_cell('''query("""
SELECT *
FROM trial_context
LIMIT 10
""")'''),
    nbf.v4.new_markdown_cell('''## Inspect a plan

The example below finds a functional run ID from the current database, then explains a 60 second event window. Replace the SELECT statement to inspect a different retrieval query.
'''),
    nbf.v4.new_code_cell('''example_run = int(query("SELECT run_id FROM runs WHERE run_type='functional' ORDER BY run_id LIMIT 1").iloc[0, 0])
print('Functional run ID', example_run)
print(query("""
EXPLAIN ANALYZE
SELECT event_id, onset_seconds
FROM events
WHERE run_id = %s AND onset_seconds < 60
ORDER BY onset_seconds, event_id
""", (example_run,)).iloc[0, 0])'''),
    nbf.v4.new_markdown_cell('''## Quick reference

| Need | Start with |
| --- | --- |
| Behavioral choices, reward and response time | `trial_context` view |
| Runs and scan metadata | `runs` |
| Trial identity and missing responses | `trials` |
| Event timing | `events` joined to `event_types` |
| Optional model estimates | `latent_values`, `variable_definitions`, `participant_fits` |

For structure, run `query('SHOW TABLES')`, `query('DESCRIBE trials')`, or `query('SHOW INDEX FROM events')`. The view `trial_context` joins the core behavioral tables; it is a regular view, not a materialized table.
'''),
]

notebook = nbf.v4.new_notebook(
    cells=cells,
    metadata={
        'kernelspec': {'display_name': 'NeuroDB', 'language': 'python', 'name': 'neurodb'},
        'language_info': {'name': 'python'},
    },
)
destination = ROOT / 'notebooks/SQL_Playground.ipynb'
nbf.write(notebook, destination)
print(destination.relative_to(ROOT))
