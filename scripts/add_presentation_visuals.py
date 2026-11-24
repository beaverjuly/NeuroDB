"""Embed the saved presentation figures as portable notebook attachments.

The script is idempotent and preserves all executed code cells and outputs.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'notebooks/NeuroDB_Demo.ipynb'
FIGURES = ROOT / 'results/presentation'

VISUALS = {
    '# NeuroDB': [('trial_timeline.png', 'Observed trial timeline and linked records')],
    '## Acquisition and validation': [('run_crosswalk.png', 'Observed behavioral and timing run crosswalk')],
    '## Database structure': [
        ('model_erd.png', 'Optional model entity relationships'),
        ('supporting_erd.png', 'Provenance, ingestion and parameter definition entity relationships'),
    ],
    '## Reward and event integrity': [('q4_event_patterns.png', 'Observed Q4 event patterns')],
    '## Event access and selectivity': [('index_access.png', 'Observed 60-second index plans and timings')],
    '## Cost of the extensible schema': [('wide_cost.png', 'Observed normalized and materialized query cost')],
    '## Final integrity gate': [('validation_gate.png', 'Saved validation summary')],
}


def visual_cell(filename: str, alt: str):
    payload = base64.b64encode((FIGURES / filename).read_bytes()).decode('ascii')
    return {
        'cell_type': 'markdown',
        'id': 'viz-' + filename.removesuffix('.png').replace('_', '-'),
        'metadata': {'tags': ['presentation-visual']},
        'source': [f'![{alt}](attachment:{filename})\n'],
        'attachments': {filename: {'image/png': payload}},
    }


def main():
    notebook = json.loads(NOTEBOOK.read_text())
    old_cells = [c for c in notebook['cells']
                 if 'presentation-visual' not in c.get('metadata', {}).get('tags', [])]
    for cell in old_cells:
        source = ''.join(cell.get('source', []))
        if source.startswith('# NeuroDB'):
            source = source.replace(
                'All displayed results are executed against the local MySQL database. Saved cell outputs provide an offline reference.',
                'Reported counts and timings come from the executed MySQL workload. Labeled schematic figures explain the methods; saved cell outputs provide an offline reference.')
        if cell['cell_type'] == 'code' and "docs/schema_overview.png" in source:
            png = base64.b64encode((ROOT / 'docs/schema_overview.png').read_bytes()).decode('ascii')
            for output in cell.get('outputs', []):
                if 'image/png' in output.get('data', {}):
                    output['data']['image/png'] = png
            # The executed cell displays this same file when Run All is used.
    cells = []
    inserted = set()
    for cell in old_cells:
        source = ''.join(cell.get('source', []))
        # The crosswalk diagram belongs after its table rather than under the
        # section heading, so the two can be seen together during narration.
        is_crosswalk_table = cell['cell_type'] == 'code' and 'behavior_run_number,r.run_number' in source
        if is_crosswalk_table:
            cells.append(cell)
            key = '## Acquisition and validation'
            cells.extend(visual_cell(*figure) for figure in VISUALS[key])
            inserted.add(key)
            continue
        is_schema_diagram = cell['cell_type'] == 'code' and "docs/schema_overview.png" in source
        if is_schema_diagram:
            cells.append(cell)
            key = '## Database structure'
            cells.extend(visual_cell(*figure) for figure in VISUALS[key])
            inserted.add(key)
            continue
        # Put the benchmark statement before both the plan figure and output.
        is_event_sql = cell['cell_type'] == 'markdown' and source.startswith('**SQL used for the 60-second event-window comparison**')
        if is_event_sql:
            cells.append(cell)
            key = '## Event access and selectivity'
            cells.extend(visual_cell(*figure) for figure in VISUALS[key])
            inserted.add(key)
            continue
        cells.append(cell)
        if cell['cell_type'] != 'markdown':
            continue
        for key, figures in VISUALS.items():
            if key in ('## Acquisition and validation', '## Database structure', '## Event access and selectivity'):
                continue
            if source.startswith(key):
                cells.extend(visual_cell(*figure) for figure in figures)
                inserted.add(key)
                break
    if inserted != set(VISUALS):
        raise RuntimeError(f'Missing visual locations: {set(VISUALS) - inserted}')
    notebook['cells'] = cells
    NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n')
    print(f'{len(cells)} cells; {sum(len(v) for v in VISUALS.values())} presentation figures embedded')


if __name__ == '__main__':
    main()
