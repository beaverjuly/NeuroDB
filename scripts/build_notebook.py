"""Generate the reproducible, database-backed classroom demonstration."""
from pathlib import Path
import sys
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nbformat as nbf
from neurodb import ROOT

cells=[]
def md(s):cells.append(nbf.v4.new_markdown_cell(s.strip()))
def code(s):cells.append(nbf.v4.new_code_cell(s.strip()))
md('''# NeuroDB
### A relational database for computational neuroscience

Julia (Jiahe) Yi · DSCI 551 · Fall 2026

NeuroDB integrates publicly available experimental observations, event timing records and computational model outputs into a reusable MySQL database.

This project demonstrates reproducible data integration, relational database design, meaningful query workloads and empirical evaluation of alternative physical designs.
''')
code('''from pathlib import Path
import sys, json
ROOT = Path.cwd() if (Path.cwd() / 'neurodb').is_dir() else Path.cwd().parent
sys.path.insert(0, str(ROOT))
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Markdown, Image, HTML
from neurodb.server import start
from neurodb.queries import query, execute, defaults, QUERIES
from neurodb.benchmark import summary
start()
pd.set_option('display.max_columns', 16)
pd.set_option('display.max_colwidth', 75)
display(HTML('<style>.dataframe{font-size:13px}.jp-OutputArea-output{overflow:auto}pre{white-space:pre-wrap}</style>'))
display(query('SELECT VERSION() AS mysql_version, CURRENT_USER() AS demo_user, DATABASE() AS database_name'))''')
md('''## Acquisition and validation

**Data pipeline**

Public source files → Identifier reconciliation → Data transformation → Validation → MySQL

Behavioral observations are stored in CSV files, while experimental event timestamps are stored in MATLAB files. The same experimental run can have different identifiers across these sources. The loader resolves these mismatches before combining the records.

Source file versions and SHA-256 checksums allow the imported data to be traced back to the original files. Unique keys and transactional upserts prevent duplicate records when ingestion is repeated. Each loading attempt is recorded in an audit table.
''')
code('''manifest = json.loads((ROOT / 'data/raw/manifest.json').read_text())
display(pd.DataFrame([{'source_participant_pairs': len(manifest['participants']),
                       'pinned_source_files': len(manifest['sources']),
                       'openneuro_snapshot': manifest['openneuro_version']}]))
display(query('SELECT inclusion_status, COUNT(*) AS participants FROM participants GROUP BY inclusion_status'))
display(query("SELECT exclusion_reason,COUNT(*) AS participants FROM participants WHERE inclusion_status='excluded' GROUP BY exclusion_reason"))
display(query('SELECT ingestion_id,transform_version,executed_at,status,message FROM ingestion_runs ORDER BY ingestion_id DESC LIMIT 4'))''')
code('''display(query("""SELECT p.bids_label,r.run_type,r.behavior_run_number,r.run_number,
COUNT(t.trial_id) AS trials FROM participants p JOIN sessions s USING(participant_id)
JOIN runs r USING(session_id) JOIN trials t USING(run_id)
WHERE p.bids_label IN ('sub-MBMF001502','sub-MBMF011401')
GROUP BY p.bids_label,r.run_id ORDER BY p.bids_label,r.behavior_run_number"""))
display(query('SELECT local_path,snapshot,LEFT(checksum,16) AS sha256_prefix,available_on_disk FROM source_files ORDER BY source_file_id LIMIT 6'))''')
md('''## Database structure

The core schema organizes experimental observations into participants, sessions, runs, trials and events. Task-specific attributes are stored separately, allowing the core schema to support different experimental tasks.

Foreign keys enforce relationships between records, including consistency between events and their associated trials and runs.

**Data coverage and model extension**

The core database contains behavioral and event timing data for 189 participants. Model-derived quantities were locally reproduced and validated for one pilot participant using the authors' released model code and fitted parameters.

This pilot demonstrates how computational model outputs can be integrated with observed experimental data. Additional model fits can be imported without changing the schema.

The following ER diagrams cover all 19 tables. Purple PK badges mark primary keys; teal FK badges mark foreign keys. The complete schema, including every attribute and cardinality, is available in [`sql/schema.sql`](../sql/schema.sql) and [`docs/schema.mmd`](../docs/schema.mmd).
''')
code("display(Image(filename=str(ROOT / 'docs/schema_overview.png')))")
code('''tables = ['participants','sessions','runs','trials','two_step_trial_details','events','latent_values','parameter_estimates','source_files']
display(pd.DataFrame([{'table': t, 'exact_rows': int(query('SELECT COUNT(*) AS n FROM '+t).iloc[0,0])} for t in tables]))
display(query("""SELECT table_name,ROUND(data_length/1024,1) AS data_KiB,ROUND(index_length/1024,1) AS index_KiB
FROM information_schema.tables WHERE table_schema='neurodb' AND table_type='BASE TABLE'
ORDER BY data_length+index_length DESC LIMIT 10"""))''')
md('''## Interactive query application

[Open NeuroDB Explorer](http://127.0.0.1:8765/)

The standalone application provides eight predefined queries, adjustable filters, explanatory diagrams, SQL statements, execution plans and a read-only custom SQL interface.

All live query results are retrieved directly from MySQL. Run Q1 and Q3 in the explorer during the presentation; saved Q4 and Q8 outputs below provide an additional reference.
''')
md('''## Stay behavior

How does the previous trial's outcome relate to whether a participant repeats their choice?

The `LAG` window function retrieves information from the immediately preceding trial within the same participant and run. Missed responses are filtered afterward to avoid incorrectly pairing nonconsecutive trials.

The resulting proportions summarize all eligible trial pairs and are descriptive statistics.
''')
code('''stay = execute('Q1')
display(stay)
fig, ax = plt.subplots(figsize=(7,3.5))
stay.pivot(index='prev_reward',columns='prev_transition',values='stay_probability').astype(float).plot.bar(ax=ax,color=['#303030','#aaaaaa'],rot=0)
ax.set(xlabel='Previous binary reward',ylabel='Stay probability',ylim=(0,1))
ax.legend(title='Previous transition',frameon=False)
plt.tight_layout(); plt.show()''')
md('''## Reward and event integrity

Reward summaries first aggregate within each participant and condition, then average participant rates. This gives participants equal weight. The event audit checks types as well as total counts. The three-event pattern on a missed trial is expected, not a missing-data failure.
''')
code("display(execute('Q2'))\ndisplay(execute('Q4'))")
md('''## Ordered extraction with provenance

This query retrieves experimental events in chronological order and joins them with model-derived values when available.

Each model variable is associated with a relevant event type. `LEFT JOIN`s preserve experimental events even when no corresponding model value exists. Unavailable values remain `NULL` rather than being replaced with zero.

Source URLs, file checksums and model versions allow the extracted records to be traced back to their origins.
''')
code('''p=defaults()
display(execute('Q3',p).head(12))
extraction=execute('Q8',p)
display(extraction[['bids_label','run_number','trial_number','event_name','onset_seconds','variable_name','modulator']].head(16))
display(extraction[['behavior_source','behavior_sha256','timing_source','timing_sha256','model_version']].drop_duplicates().head())''')
md('''## Physical design experiments

The archived benchmark used real observations copied into isolated event tables. The baseline retains primary, natural-key and foreign-key-supporting indexes. It is not unindexed. Alternatives add a run/onset composite index, a covering extension or reversed column order. No access hints force the optimizer.

Each comparison uses identical results, two warm-up executions and nine measurements in interleaved order. `EXPLAIN ANALYZE` runs separately from the timed query. Client timing includes result transfer; Handler counters measure handler operations, not physical disk reads.

The next cell loads the verified benchmark report so the displayed timings match the presentation figures. To intentionally refresh these machine-dependent measurements, rerun `python -m neurodb.benchmark` and rebuild the figures and saved outputs.
''')
code('''benchmark = json.loads((ROOT / 'results/benchmark.json').read_text())
measured = summary(benchmark)
display(measured.round(4))''')
md('''## Event access and selectivity

Compare the baseline and composite plans for a 60-second window. Then inspect narrow and wide windows. Look for index range access, actual rows and an explicit sort. A wide interval or a small in-memory table may show little timing benefit even when fewer records are visited.
''')
md('''**SQL used for the 60-second event-window comparison**

```sql
SELECT event_id,run_id,trial_id,event_type_id,onset_seconds,duration_seconds
FROM bench_events_baseline
WHERE run_id=%s AND onset_seconds >= %s AND onset_seconds < %s
ORDER BY onset_seconds,event_id
```

The bound values are `(35, 0.0, 60.0)`. The composite, covering and reversed comparisons use the same statement and values, replacing only `bench_events_baseline` with their corresponding table name. Each copy contains identical event records.
''')
code('''for name in ['baseline','composite','covering','reversed']:
    print(name.upper())
    print(benchmark['event_experiments']['60'][name]['explain_analyze'])
    print()
display(pd.DataFrame(benchmark['indexes']['production_events'])[['Key_name','Seq_in_index','Column_name','Non_unique']])''')
code('''event_results=measured[measured.experiment=='event window']
fig,axes=plt.subplots(1,2,figsize=(11,3.6))
styles=['-','--',':','-.']
for i,(name,g) in enumerate(event_results.groupby('design',sort=False)):
    axes[0].plot(g.window_seconds,g.median_ms,styles[i],marker='o',label=name,color=str(.15+i*.18))
    axes[1].plot(g.window_seconds,g.handler_reads,styles[i],marker='o',label=name,color=str(.15+i*.18))
axes[0].set(xlabel='Window seconds',ylabel='Median execute and fetch ms')
axes[1].set(xlabel='Window seconds',ylabel='Handler read operations')
axes[1].legend(frameon=False,fontsize=9)
plt.tight_layout();plt.show()''')
md('''## Cost of the extensible schema

The generic query joins the core and the task-specific detail table. The wide copy prejoins exactly the same rows and repeats participant/run attributes. Both queries return identical participant-level reward aggregates. The wide representation incurs refresh work and duplicates data; it does not replace the canonical normalized tables.
''')
code('''display(measured[measured.experiment=='behavior aggregation'].round(4))
display(pd.DataFrame([{'wide_rows':benchmark['wide_rows'],
                       'wide_serialized_MiB':benchmark['wide_serialized_json_bytes']/1024**2,
                       'wide_data_MiB':benchmark['wide_physical_storage']['DATA_LENGTH']/1024**2,
                       'wide_index_MiB':benchmark['wide_physical_storage']['INDEX_LENGTH']/1024**2,
                       'refresh_ms':benchmark['wide_refresh_ms']}]))
print(benchmark['storage_note'])
for name in ['generic_joins','wide_materialized']:
    print(name.upper());print(benchmark['extensibility'][name]['explain_analyze']);print()''')
md('''## Pilot model integration

Q5 and Q6 demonstrate how computational model outputs can be queried alongside observed behavior.

The current model extension contains validated outputs for one pilot participant. Q5 compares prediction errors across transition types. Q6 compares action preferences estimated by two computational mechanisms.

These queries demonstrate relational integration and consistency of model-derived data rather than population-level scientific findings.
''')
code("display(execute('Q5'))\ndisplay(execute('Q6'))")
md('''## Final integrity gate

The final checks cover source checksums, foreign-key consistency, trial/event patterns, pilot counts, model ownership and an independent implementation of the stay query. The source cohort, validated database cohort and published analytic cohort are separate denominators. No voxel data or new fMRI inference are included.
''')
code('''from neurodb.validate import validate
validation=validate()
display(pd.DataFrame([{'check':k,'passed':v} for k,v in validation['checks'].items()]))
assert validation['passed']
print('All database validation gates passed.')''')
md('''## Reference materials

| Material | Location |
| --- | --- |
| Classroom speaking guide | `docs/DEMO_GUIDE.md` |
| Source mapping and limitations | `docs/DATA_DICTIONARY.md` |
| Executable relational schema | `sql/schema.sql` |
| Saved plans and measurements | `results/benchmark.json` |
| Load and validation audit | `results/validation.json` |
| MySQL execution plan reference | https://dev.mysql.com/doc/refman/8.4/en/explain.html |
| Public observations | https://osf.io/ctfzd/ |
| OpenNeuro snapshot | https://openneuro.org/datasets/ds007474/versions/1.0.5 |
''')
nb=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'NeuroDB','language':'python','name':'neurodb'},'language_info':{'name':'python'}})
nbf.write(nb,ROOT/'notebooks/NeuroDB_Demo.ipynb')
subprocess.check_call([sys.executable, str(ROOT/'scripts/build_presentation_visuals.py')])
subprocess.check_call([sys.executable, str(ROOT/'scripts/add_presentation_visuals.py')])
print('Generated notebooks/NeuroDB_Demo.ipynb with presentation figures')
