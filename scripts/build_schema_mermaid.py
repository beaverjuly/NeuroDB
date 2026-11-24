"""Generate the complete keyed Mermaid ERD from the executable MySQL schema."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
sql = (ROOT / 'sql/schema.sql').read_text()
relationships = '''
    studies ||--o{ participants : contains
    participants ||--o{ sessions : attends
    sessions ||--o{ runs : contains
    runs ||--o{ trials : contains
    runs ||--o{ events : contains
    trials o|--o{ events : optionally_links
    trials ||--o| two_step_trial_details : extends
    participants ||--o{ participant_measures : describes
    model_specifications ||--o{ fitting_jobs : versions
    model_specifications ||--o{ parameter_definitions : defines
    model_specifications ||--o{ variable_definitions : defines
    fitting_jobs ||--o{ participant_fits : produces
    participants ||--o{ participant_fits : fitted
    participant_fits ||--o{ parameter_estimates : estimates
    participant_fits ||--o{ latent_values : produces
    trials ||--o{ latent_values : aligns
    variable_definitions ||--o{ latent_values : labels
    event_types ||--o{ events : classifies
    event_types o|--o{ variable_definitions : locks
    source_files ||--o{ ingestion_records : audits
    ingestion_runs ||--o{ ingestion_records : records
    source_files ||--o{ participants : supplies
    source_files ||--o{ runs : supplies
    source_files ||--o{ trials : supplies
    source_files ||--o{ events : supplies
    source_files ||--o{ participant_measures : supplies
    source_files ||--o{ participant_fits : supplies
'''


def declarations(body):
    """Split SQL declarations at top-level commas, including ENUM and keys."""
    parts, current, depth, quote = [], [], 0, False
    for char in body:
        if char == "'":
            quote = not quote
        elif not quote and char == '(':
            depth += 1
        elif not quote and char == ')':
            depth -= 1
        if char == ',' and depth == 0 and not quote:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append(''.join(current).strip())
    return parts


def main():
    blocks = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\) ENGINE=InnoDB;', sql, re.S)
    if len(blocks) != 19:
        raise RuntimeError(f'Expected 19 tables, found {len(blocks)}')
    output = ['erDiagram']
    for table, body in blocks:
        lines = declarations(body)
        primary = set()
        foreign = set()
        for line in lines:
            match = re.search(r'\bPRIMARY KEY\s*\(([^)]+)\)', line)
            if match:
                primary.update(item.strip() for item in match.group(1).split(','))
            match = re.search(r'\bFOREIGN KEY\s*\(([^)]+)\)', line)
            if match:
                foreign.update(item.strip() for item in match.group(1).split(','))
        fields = []
        for line in lines:
            match = re.match(r'(\w+)\s+([A-Z]+)', line)
            if not match or match.group(1).upper() in {'PRIMARY', 'FOREIGN', 'UNIQUE', 'KEY', 'CHECK'}:
                continue
            name, datatype = match.groups()
            if 'PRIMARY KEY' in line:
                primary.add(name)
            fields.append((name, datatype))
        output.append(f'    {table} {{')
        for name, datatype in fields:
            flags = ','.join(flag for flag, present in [('PK', name in primary), ('FK', name in foreign)] if present)
            output.append(f'        {datatype.lower()} {name}' + (f' {flags}' if flags else ''))
        output.append('    }')
    output.extend(relationships.rstrip().splitlines())
    path = ROOT / 'docs/schema.mmd'
    path.write_text('\n'.join(output) + '\n')
    print(f'{path.relative_to(ROOT)}: {len(blocks)} entities, all SQL attributes and keyed relationships')


if __name__ == '__main__':
    main()
