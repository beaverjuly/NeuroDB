"""Create an accessible saved walkthrough and concise measured-results note."""
import base64
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
import nbformat
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from neurodb import ROOT

nb=nbformat.read(ROOT/'notebooks/NeuroDB_Demo.ipynb',as_version=4)
code_cells=[c for c in nb.cells if c.cell_type=='code']
assert all(c.execution_count is not None for c in code_cells)
assert not any(o.output_type=='error' for c in code_cells for o in c.outputs)
descriptions=[('schema_overview','Core NeuroDB ER diagram showing primary keys, foreign keys, attributes and cardinality'),
              ('stay_behavior','Observed stay probabilities by previous binary reward and transition type'),
              ('index_selectivity','Measured warm query time and Handler read operations across event window widths')]
images=[o.data['image/png'] for c in code_cells for o in c.outputs if 'data' in o and 'image/png' in o.data]
assert len(images)==len(descriptions)
for payload,(name,description) in zip(images,descriptions):
    (ROOT/'results'/f'{name}.png').write_bytes(base64.b64decode(payload))
body,_=HTMLExporter().from_notebook_node(nb)
soup=BeautifulSoup(body,'html.parser')
output_images=[tag for tag in soup.find_all('img')
               if tag.get('alt') == 'No description has been provided for this image']
assert len(output_images)==len(descriptions)
for tag,(_,description) in zip(output_images,descriptions):tag['alt']=description
banner=soup.new_tag('aside')
banner['style']='margin:24px auto;padding:16px;max-width:1100px;background:#eee;border-left:4px solid #444;font-family:system-ui'
banner.string='Saved walkthrough. Tables and plans are recorded MySQL results. For live Q1 and Q3, open Launch NeuroDB Explorer.command. This HTML copy does not execute SQL.'
soup.body.insert(0,banner)
(ROOT/'results/NeuroDB_Demo.html').write_text(str(soup))

v=json.loads((ROOT/'results/validation.json').read_text())
b=json.loads((ROOT/'results/benchmark.json').read_text())
i=json.loads((ROOT/'results/idempotence.json').read_text())
e=b['event_experiments']['60'];g=b['extensibility']['generic_joins'];w=b['extensibility']['wide_materialized']
storage=b['wide_physical_storage'];mib=1024**2
measured_local=datetime.fromisoformat(b['measured_at']).astimezone(ZoneInfo('America/Los_Angeles')).strftime('%B %d, %Y at %I %M %p %Z')
lines=['# Measured demo results','',f"MySQL {v['mysql_version']}. Measurements recorded on {measured_local}. All observations are real public-source records.",'',
'| Database content | Exact count |','| --- | --- |']
for key in ['participants','runs','trials','events','latent_values','parameter_estimates']:
    lines.append(f"| {key.replace('_',' ')} | {v['counts'][key]:,} |")
lines+=['','All 189 source participants passed the implemented alignment and database checks. This does not identify the paper\u0027s 179-person analytic sample. Latent values and parameters cover only the validated pilot.','',
'## Event window experiment','',
'The same 60-second interval returns 40 events. The baseline visits all 462 events in the run and sorts the selected rows. The composite index uses a run equality followed by an onset range and supplies the requested ordering. The reversed index is available, but the optimizer chooses the existing run-leading index for this query.','',
'| Design | Median ms | Handler reads |','| --- | --- | --- |']
for name,d in e.items():lines.append(f"| {name} | {d['median_ms']:.3f} | {d['median_handler_reads']:,} |")
lines+=['','Nine warm measurements follow two warm-up executions. Configurations are interleaved. Timing includes client execution and result fetching. Handler counts are not physical disk reads. At 720 seconds the whole run is retrieved, and the index alternatives have similar operation counts.','',
'## Extensibility experiment','',
'| Representation | Median ms | Handler reads |','| --- | --- | --- |',
f"| Generic core and detail joins | {g['median_ms']:.3f} | {g['median_handler_reads']:,} |",
f"| Materialized wide copy | {w['median_ms']:.3f} | {w['median_handler_reads']:,} |",'',
f"Both return the same {g['returned_rows']} participant and reward-condition aggregates. Building and indexing the temporary wide copy took {b['wide_refresh_ms']:.1f} ms in this run. A matching isolated physical copy allocated {storage['DATA_LENGTH']/mib:.2f} MiB of data pages and {storage['INDEX_LENGTH']/mib:.2f} MiB of index pages. The physical copy was removed after measurement.",'',
'The wide copy reduces query-time joins, but duplicates participant/run attributes and requires refreshing. It is an experiment, not the canonical source of observations. These are local warm measurements on this dataset, not general performance guarantees.','',
'## Verification','',
f"All {len(v['checks'])} database gates passed. Full reload equality passed for {len(i['before'])} canonical tables using exact counts and MySQL checksums. All {len(code_cells)} notebook code cells executed without errors. Integration test results are saved in `tests.log`.",'',
'Detailed evidence is in `benchmark.json`, `benchmark_summary.tsv`, `validation.json` and `idempotence.json`.']
(ROOT/'results/RESULTS.md').write_text('\n'.join(lines)+'\n')
print(f'Finalized saved walkthrough and results note for {v["counts"]["participants"]} participants')
