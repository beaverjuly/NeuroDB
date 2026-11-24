"""Build the notebook's presentation figures from saved, validated results.

These figures explain records and query plans. The benchmark values and event
onsets come from the archived outputs, so regenerating them needs no MySQL.
"""
from __future__ import annotations

import csv
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/presentation'
OUT.mkdir(parents=True, exist_ok=True)

NAVY = '#17324d'
BLUE = '#276c9b'
TEAL = '#18877c'
ORANGE = '#c06b28'
PURPLE = '#75569c'
INK = '#1d2c3b'
MUTED = '#576d80'
PALE = '#f5f8fb'
LINE = '#d7e2eb'
GREEN = '#2d8666'


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False):
    names = (
        ['/System/Library/Fonts/Supplemental/Arial Bold.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'] if bold else
        ['/System/Library/Fonts/Supplemental/Arial.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    )
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)


def canvas(height, title, subtitle):
    image = Image.new('RGB', (1600, height), 'white')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 22, 1572, height - 22), radius=24,
                           fill='white', outline=LINE, width=2)
    draw.rounded_rectangle((28, 22, 1572, 132), radius=24, fill=NAVY)
    draw.rectangle((28, 90, 1572, 132), fill=NAVY)
    draw.text((66, 38), title, font=font(42, True), fill='white')
    draw.text((68, 94), subtitle, font=font(24), fill='#d5e5f1')
    return image, draw


def text(draw, x, y, value, size=28, color=INK, bold=False):
    draw.text((x, y), str(value), font=font(size, bold), fill=color)


def centered(draw, x, y, value, size=28, color=INK, bold=False):
    face = font(size, bold)
    w = draw.textbbox((0, 0), str(value), font=face)[2]
    text(draw, x - w / 2, y, value, size, color, bold)


def box(draw, bounds, fill=PALE, outline=LINE, radius=16):
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=2)


def arrow(draw, start, end, color=BLUE, width=5):
    draw.line((start, end), fill=color, width=width)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max((dx * dx + dy * dy) ** .5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = end
    base = (end[0] - ux * 17, end[1] - uy * 17)
    draw.polygon([tip, (base[0] + px * 9, base[1] + py * 9),
                  (base[0] - px * 9, base[1] - py * 9)], fill=color)


def save(image, name):
    path = OUT / name
    image.save(path, optimize=True)
    print(path.relative_to(ROOT), path.stat().st_size)


def schema_card(draw, bounds, title, rows, color=BLUE):
    """One readable entity with key status and representative stored attributes."""
    x0, y0, x1, y1 = bounds
    box(draw, bounds, fill='white', outline=LINE, radius=12)
    draw.rounded_rectangle((x0, y0, x1, y0 + 48), radius=12, fill=color)
    draw.rectangle((x0, y0 + 27, x1, y0 + 48), fill=color)
    text(draw, x0 + 18, y0 + 8, title, 27, 'white', True)
    row_y = y0 + 61
    for badge, field in rows:
        if badge:
            badge_color = PURPLE if 'PK' in badge else TEAL
            badge_width = 82 if badge == 'PK/FK' else 45
            box(draw, (x0 + 17, row_y + 2, x0 + 17 + badge_width, row_y + 31),
                fill=badge_color, outline=badge_color, radius=5)
            text(draw, x0 + 23, row_y + 5, badge, 17 if badge == 'PK/FK' else 18, 'white', True)
        text(draw, x0 + 112, row_y + 2, field, 23, INK, bool(badge))
        row_y += 34


def relation(draw, points, label, color=MUTED, label_at=None):
    draw.line(points, fill=color, width=3, joint='curve')
    arrow(draw, points[-2], points[-1], color, 3)
    if label_at:
        x, y = label_at
        width = draw.textbbox((0, 0), label, font=font(20, True))[2]
        box(draw, (x - 8, y - 3, x + width + 8, y + 27),
            fill='white', outline='white', radius=4)
        text(draw, x, y, label, 20, color, True)


def core_erd():
    """Presentation ERD for the experimental hierarchy and its event records."""
    image, d = canvas(1240, 'Database structure: experimental records',
                      'PK = primary key   FK = foreign key   arrows show parent 1 to child 0..many')
    cards = {
        'studies': (65, 180, 520, 347),
        'participants': (573, 180, 1028, 381),
        'sessions': (1081, 180, 1536, 347),
        'runs': (65, 456, 520, 691),
        'trials': (573, 456, 1028, 691),
        'details': (1081, 456, 1536, 691),
        'types': (65, 769, 520, 936),
        'events': (573, 769, 1028, 1040),
        'sources': (1081, 769, 1536, 936),
    }
    # Draw connections first so all lines sit behind entity cards.
    relation(d, [(520, 263), (573, 263)], '1 → 0..*')
    relation(d, [(1028, 263), (1081, 263)], '1 → 0..*')
    relation(d, [(1308, 347), (1308, 416), (292, 416), (292, 456)],
             '1 → 0..*', label_at=(777, 385))
    relation(d, [(520, 558), (573, 558)], '1 → 0..*')
    relation(d, [(1028, 558), (1081, 558)], '1 → 0..1')
    relation(d, [(292, 691), (292, 728), (648, 728), (648, 769)],
             '1 → 0..*', label_at=(355, 696))
    relation(d, [(800, 691), (800, 769)], '1 → 0..*', label_at=(810, 720))
    relation(d, [(520, 853), (573, 853)], '1 → 0..*')
    relation(d, [(1081, 853), (1028, 853)], '1 → 0..*')
    schema_card(d, cards['studies'], 'studies',
                [('PK', 'study_id'), ('', 'accession'), ('', 'title')])
    schema_card(d, cards['participants'], 'participants',
                [('PK', 'participant_id'), ('FK', 'study_id'),
                 ('', 'bids_label'), ('FK', 'source_file_id')])
    schema_card(d, cards['sessions'], 'sessions',
                [('PK', 'session_id'), ('FK', 'participant_id'), ('', 'session_label')])
    schema_card(d, cards['runs'], 'runs',
                [('PK', 'run_id'), ('FK', 'session_id'), ('', 'run_number'),
                 ('', 'behavior_run_number'), ('FK', 'source_file_id')])
    schema_card(d, cards['trials'], 'trials',
                [('PK', 'trial_id'), ('FK', 'run_id'), ('', 'trial_number'),
                 ('', 'response_valid'), ('FK', 'source_file_id')])
    schema_card(d, cards['details'], 'two_step_trial_details',
                [('PK/FK', 'trial_id'),
                 ('', 'chosen_ship'), ('', 'reward'), ('', 'transition_type')], ORANGE)
    schema_card(d, cards['types'], 'event_types',
                [('PK', 'event_type_id'), ('', 'event_name'),
                 ('', 'trial_status_rules')], TEAL)
    schema_card(d, cards['events'], 'events',
                [('PK', 'event_id'), ('FK', 'run_id'), ('FK', 'trial_id'),
                 ('FK', 'event_type_id'), ('', 'onset_seconds'),
                 ('FK', 'source_file_id')], TEAL)
    schema_card(d, cards['sources'], 'source_files',
                [('PK', 'source_file_id'), ('', 'source_url'), ('', 'checksum')], PURPLE)
    text(d, 70, 1068, 'Trial → detail is 1 to 0..1. Event (run_id, trial_id) references Trial (run_id, trial_id).',
         25, NAVY, True)
    text(d, 70, 1108, 'An event may have NULL trial_id for a run-level event. Source files also link to participants, runs and trials.',
         23, MUTED)
    text(d, 70, 1145, 'Additional entities and relationships appear in the model and provenance panels.', 23, MUTED)
    save(image, 'core_erd.png')
    image.save(ROOT / 'docs/schema_overview.png', optimize=True)
    image.save(ROOT / 'results/schema_overview.png', optimize=True)


def model_erd():
    image, d = canvas(1010, 'Database structure: optional model extension',
                      'A validated fit can add trial-level estimates without changing the observed trials')
    cards = {
        'models': (70, 190, 510, 388),
        'jobs': (580, 190, 1020, 388),
        'fits': (1090, 190, 1530, 422),
        'variables': (70, 520, 510, 752),
        'latents': (580, 520, 1020, 786),
        'parameters': (1090, 520, 1530, 752),
    }
    relation(d, [(510, 280), (580, 280)], '1 → 0..*')
    relation(d, [(1020, 280), (1090, 280)], '1 → 0..*')
    relation(d, [(280, 388), (280, 520)], '1 → 0..*', label_at=(291, 445))
    relation(d, [(1310, 422), (1310, 475), (800, 475), (800, 520)],
             '1 → 0..*', label_at=(1060, 441))
    relation(d, [(510, 650), (580, 650)], '1 → 0..*')
    relation(d, [(1310, 422), (1310, 520)], '1 → 0..*', label_at=(1320, 455))
    schema_card(d, cards['models'], 'model_specifications',
                [('PK', 'model_id'), ('', 'model_name'), ('', 'version'),
                 ('', 'code_reference')], PURPLE)
    schema_card(d, cards['jobs'], 'fitting_jobs',
                [('PK', 'job_id'), ('FK', 'model_id'), ('', 'fitting_method'),
                 ('', 'code_version')], PURPLE)
    schema_card(d, cards['fits'], 'participant_fits',
                [('PK', 'fit_id'), ('FK', 'job_id'), ('FK', 'participant_id'),
                 ('', 'fit_status'), ('FK', 'source_file_id')], PURPLE)
    schema_card(d, cards['variables'], 'variable_definitions',
                [('PK', 'variable_id'), ('FK', 'model_id'),
                 ('FK', 'locking_event_type_id'), ('', 'variable_name'),
                 ('', 'stage')], PURPLE)
    schema_card(d, cards['latents'], 'latent_values',
                [('PK/FK', 'fit_id'), ('PK/FK', 'trial_id'),
                 ('PK/FK', 'variable_id'),
                 ('', 'value')], PURPLE)
    schema_card(d, cards['parameters'], 'parameter_estimates',
                [('PK/FK', 'fit_id'), ('PK', 'parameter_name'),
                 ('', 'raw_value'), ('', 'applied_value')], PURPLE)
    box(d, (70, 827, 1530, 924), fill='#f4f0f8', outline='#e2d7ec')
    text(d, 92, 840, 'Cross-links to the core', 27, PURPLE, True)
    text(d, 92, 881, 'participant_fits.participant_id → participants; latent_values.trial_id → trials; variable event type → event_types',
         23, INK)
    text(d, 70, 953, 'Multiple PK badges in one entity form a composite primary key. The third panel shows supporting entities.',
         23, MUTED)
    save(image, 'model_erd.png')


def supporting_erd():
    """Complete the 19-table ERD with ingestion, measures and parameter metadata."""
    image, d = canvas(1260, 'Database structure: provenance and definitions',
                      'The third ERD panel completes the 19-table schema · PK and FK badges identify keys')
    cards = {
        'source': (70, 180, 510, 414),
        'ingestion': (580, 180, 1020, 414),
        'records': (1090, 180, 1530, 448),
        'participants': (70, 570, 510, 770),
        'measures': (580, 570, 1020, 838),
        'models': (70, 920, 510, 1120),
        'definitions': (580, 920, 1020, 1154),
    }
    relation(d, [(1020, 289), (1090, 289)], '1 → 0..*')
    relation(d, [(290, 414), (290, 490), (1310, 490), (1310, 448)],
             '1 → 0..*', label_at=(680, 455))
    relation(d, [(510, 680), (580, 680)], '1 → 0..*')
    relation(d, [(410, 414), (410, 520), (800, 520), (800, 570)],
             '1 → 0..*', label_at=(575, 491))
    relation(d, [(510, 1020), (580, 1020)], '1 → 0..*')
    schema_card(d, cards['source'], 'source_files',
                [('PK', 'source_file_id'), ('', 'local_path'),
                 ('', 'source_url'), ('', 'checksum'), ('', 'snapshot')], PURPLE)
    schema_card(d, cards['ingestion'], 'ingestion_runs',
                [('PK', 'ingestion_id'), ('', 'transform_version'),
                 ('', 'code_checksum'), ('', 'executed_at'), ('', 'status')], ORANGE)
    schema_card(d, cards['records'], 'ingestion_records',
                [('PK/FK', 'ingestion_id'), ('PK/FK', 'source_file_id'),
                 ('', 'rows_loaded'),
                 ('', 'validation_status')], ORANGE)
    schema_card(d, cards['participants'], 'participants',
                [('PK', 'participant_id'), ('FK', 'study_id'),
                 ('', 'bids_label'), ('FK', 'source_file_id')])
    schema_card(d, cards['measures'], 'participant_measures',
                [('PK/FK', 'participant_id'),
                 ('PK', 'measure_name'), ('PK', 'method_version'),
                 ('FK', 'source_file_id'), ('', 'value')], BLUE)
    schema_card(d, cards['models'], 'model_specifications',
                [('PK', 'model_id'), ('', 'model_name'),
                 ('', 'version'), ('', 'code_reference')], PURPLE)
    schema_card(d, cards['definitions'], 'parameter_definitions',
                [('PK/FK', 'model_id'), ('PK', 'parameter_name'),
                 ('', 'transform'), ('', 'lower_bound'),
                 ('', 'upper_bound')], PURPLE)
    text(d, 1080, 590, 'Each arrow', 27, NAVY, True)
    text(d, 1080, 631, '1 → 0..many', 28, BLUE, True)
    text(d, 1080, 689, 'The child holds', 25, MUTED)
    text(d, 1080, 725, 'the foreign key.', 25, MUTED)
    text(d, 70, 1188, 'Multiple PK badges form a composite key. The complete attribute inventory is in docs/schema.mmd.',
         24, NAVY, True)
    save(image, 'supporting_erd.png')


def read_tsv(name):
    with (ROOT / 'results' / name).open(newline='') as handle:
        return list(csv.DictReader(handle, delimiter='\t'))


q3 = read_tsv('Q3.tsv')
q8 = read_tsv('Q8.tsv')
benchmark = json.loads((ROOT / 'results/benchmark.json').read_text())
validation = json.loads((ROOT / 'results/validation.json').read_text())


def trial_timeline():
    first_trial = [row for row in q8 if row['trial_number'] == '1'][:6]
    assert len(first_trial) == 6
    image, d = canvas(615, 'One decision episode becomes linked records',
                      'Observed pilot example · sub-MBMF001502 · functional run 1 · trial 1')
    x0, x1, y = 135, 1460, 275
    d.line((x0, y, x1, y), fill=LINE, width=8)
    for sec in range(7):
        x = x0 + (x1 - x0) * sec / 6
        d.line((x, y - 12, x, y + 12), fill=MUTED, width=3)
        centered(d, x, y + 24, str(sec) + ' s', 22, MUTED)
    colors = [BLUE, BLUE, TEAL, TEAL, TEAL, ORANGE]
    for i, row in enumerate(first_trial):
        onset = float(row['onset_seconds'])
        x = x0 + (x1 - x0) * onset / 6
        d.ellipse((x - 11, y - 11, x + 11, y + 11), fill=colors[i], outline='white', width=2)
        label = row['event_name'].replace('_right', '').replace('_left', '')
        label_y = 177 if i % 2 == 0 else 347
        d.line((x, y - 15 if i % 2 == 0 else y + 15,
                x, label_y + 46 if i % 2 == 0 else label_y - 8), fill=colors[i], width=2)
        centered(d, x, label_y, label, 24, colors[i], True)
    cards = [
        ('Behavior CSV', 'choice = 2   reward = 1', BLUE),
        ('Timing MAT', 'six event onsets from 0.02 to 5.90 s', TEAL),
        ('Optional model fit', 'stage one SPE at planet = 0.30', PURPLE),
    ]
    for i, (heading, detail, color) in enumerate(cards):
        left = 70 + i * 500
        box(d, (left, 423, left + 460, 532))
        d.rectangle((left + 1, 424, left + 11, 531), fill=color)
        text(d, left + 28, 438, heading, 28, color, True)
        text(d, left + 28, 482, detail, 24, INK)
    text(d, 70, 555, 'Event times are relative to the run. No voxel signal is stored in NeuroDB.', 24, MUTED)
    save(image, 'trial_timeline.png')


def run_crosswalk():
    image, d = canvas(590, 'Run numbers must be reconciled',
                      'Actual records shown in the notebook crosswalk table')
    groups = [
        ('sub-MBMF001502', [('1', 'structural 1'), ('2', 'functional 1'), ('3', 'functional 2')]),
        ('sub-MBMF011401', [('1', 'functional 1'), ('2', 'functional 2'), ('3', 'structural 1')]),
    ]
    for group_index, (name, rows) in enumerate(groups):
        left = 66 + group_index * 766
        box(d, (left, 158, left + 706, 478))
        text(d, left + 24, 176, name, 30, NAVY, True)
        text(d, left + 24, 222, 'behavior_run_number', 24, MUTED, True)
        text(d, left + 431, 222, 'run_type + run_number', 24, MUTED, True)
        for i, (behavior, timing) in enumerate(rows):
            y = 273 + i * 63
            box(d, (left + 38, y, left + 265, y + 48), fill='#e9f1f8', outline='#e9f1f8', radius=9)
            centered(d, left + 151, y + 9, 'run ' + behavior, 26, BLUE, True)
            arrow(d, (left + 274, y + 24), (left + 413, y + 24), MUTED, 3)
            box(d, (left + 428, y, left + 668, y + 48), fill='#e7f5f0', outline='#e7f5f0', radius=9)
            centered(d, left + 548, y + 9, timing, 24, TEAL, True)
    text(d, 70, 503, 'The same behavior run number can describe different run types across participants.', 26, INK, True)
    text(d, 70, 544, 'The loader checks identity, run type and timing alignment before it creates the database link.', 24, MUTED)
    save(image, 'run_crosswalk.png')


def q1_adjacency():
    image, d = canvas(535, 'Q1 uses the immediately preceding trial',
                      'Illustration of LAG within one participant and run · examples are schematic')
    rows = [
        ('Trial 1', 'choice A', 'rewarded', BLUE),
        ('Trial 2', 'missed', 'no choice', ORANGE),
        ('Trial 3', 'choice B', 'valid', BLUE),
        ('Trial 4', 'choice B', 'valid', BLUE),
    ]
    for i, (trial, choice, status, color) in enumerate(rows):
        left = 68 + i * 385
        box(d, (left, 183, left + 340, 331), fill='#f5f8fb')
        d.rectangle((left + 1, 184, left + 12, 330), fill=color)
        text(d, left + 29, 199, trial, 30, NAVY, True)
        text(d, left + 29, 243, choice, 28, color, True)
        text(d, left + 29, 287, status, 24, MUTED)
        if i < 3:
            arrow(d, (left + 345, 258), (left + 377, 258), MUTED, 3)
    box(d, (68, 365, 781, 452), fill='#fff4e8', outline='#f3d6b8')
    text(d, 90, 380, 'Trial 2 → 3 is excluded', 28, ORANGE, True)
    text(d, 90, 418, 'The previous response was missed.', 24, INK)
    box(d, (820, 365, 1530, 452), fill='#eaf5f1', outline='#b5dcd0')
    text(d, 842, 380, 'Trial 3 → 4 is eligible', 28, GREEN, True)
    text(d, 842, 418, 'Same choice, so stay = 1.', 24, INK)
    text(d, 70, 473, 'LAG is computed first. Filtering valid responses afterward cannot skip a missed trial.', 24, MUTED)
    save(image, 'q1_adjacency.png')


def q3_window():
    assert len(q3) == benchmark['event_experiments']['60']['baseline']['returned_rows'] == 40
    image, d = canvas(560, 'Q3 selects events in one run and time window',
                      'Observed run 35 · 462 total events · 40 events from 0 to under 60 seconds')
    text(d, 72, 170, '0–720 second comparison interval covers the run', 28, NAVY, True)
    box(d, (72, 218, 1518, 269), fill='#e9eef3', outline='#e9eef3', radius=11)
    d.rounded_rectangle((72, 218, 72 + 1446 * 60 / 720, 269), radius=11, fill='#a7d5cd')
    text(d, 75, 280, '0 s', 23, MUTED)
    text(d, 1440, 280, '720 s', 23, MUTED)
    text(d, 72, 347, 'Zoom into the selected 0–60 second interval', 28, NAVY, True)
    x0, x1, y = 92, 1490, 425
    d.line((x0, y, x1, y), fill=LINE, width=8)
    for sec in range(0, 61, 10):
        x = x0 + (x1 - x0) * sec / 60
        d.line((x, y - 12, x, y + 12), fill=MUTED, width=2)
        centered(d, x, y + 24, str(sec), 22, MUTED)
    for row in q3:
        x = x0 + (x1 - x0) * float(row['onset_seconds']) / 60
        color = ORANGE if row['event_name'] == 'outcome' else TEAL
        d.ellipse((x - 5, y - 26, x + 5, y - 16), fill=color)
    text(d, 72, 499, 'WHERE run_id = 35 AND onset ≥ 0 AND onset < 60    ORDER BY onset, event_id', 26, INK, True)
    save(image, 'q3_window.png')


def event_patterns():
    image, d = canvas(510, 'Q4 checks expected event patterns',
                      'Actual functional trial totals · Q4 verifies both counts and event types')
    rows = [
        ('Completed', '28,512 trials', ['fixation', 'stimulus', 'response', 'planet', 'pad', 'outcome'], TEAL),
        ('Missed', '594 trials', ['fixation', 'stimulus', 'missing response'], ORANGE),
    ]
    for i, (title, count, events, color) in enumerate(rows):
        y = 174 + i * 150
        text(d, 70, y, title, 32, color, True)
        text(d, 70, y + 44, count + ' · ' + str(len(events)) + ' events', 25, MUTED)
        left, width = 333, 192
        for j, event in enumerate(events):
            x = left + j * 205
            box(d, (x, y + 6, x + width, y + 68), fill='#e9f4f1' if i == 0 else '#fff1e5',
                outline='#c6e1d8' if i == 0 else '#f1d8bd', radius=11)
            centered(d, x + width / 2, y + 22, event, 23, color, True)
            if j + 1 < len(events):
                arrow(d, (x + width + 2, y + 37), (x + 205, y + 37), MUTED, 2)
    text(d, 70, 458, 'No planet, pad or outcome event is invented after a missed response.', 26, INK, True)
    save(image, 'q4_event_patterns.png')


def provenance():
    image, d = canvas(615, 'Q8 keeps observations and provenance together',
                      'Observed pilot example · trial 1 planet event · optional model value')
    sources = [
        (70, 'Behavior CSV', 'choice 2 · reward 1', 'source URL + SHA256', BLUE),
        (570, 'Timing MAT', 'planet at 2.94 s', 'source URL + SHA256', TEAL),
        (1070, 'Model fit', 'SPE = 0.30', 'fit source + version', PURPLE),
    ]
    for x, heading, detail, audit, color in sources:
        box(d, (x, 177, x + 450, 335))
        d.rectangle((x + 1, 178, x + 12, 334), fill=color)
        text(d, x + 32, 194, heading, 30, color, True)
        text(d, x + 32, 240, detail, 27, INK)
        text(d, x + 32, 286, audit, 23, MUTED)
        arrow(d, (x + 225, 341), (x + 225, 389), color, 4)
    box(d, (208, 403, 1392, 501), fill='#edf3f8', outline='#cddce8')
    centered(d, 800, 418, 'One ordered event record with linked trial fields and source identity', 29, NAVY, True)
    centered(d, 800, 461, 'The model value joins only when the validated fit and event stage match.', 25, MUTED)
    text(d, 72, 537, 'Absent model values remain NULL. Model-derived fields currently cover one validated pilot.', 25, INK, True)
    save(image, 'q8_provenance.png')


def index_access():
    sixty = benchmark['event_experiments']['60']
    image, d = canvas(775, 'Index order changes how MySQL reaches 40 events',
                      '60-second window in run 35 · measured from identical event-table copies')
    rows = [
        ('BASELINE', 'run lookup → 462 rows → time filter → 40 rows → sort', BLUE, 'baseline'),
        ('COMPOSITE', '(run, onset) range scan → 40 rows → already ordered', TEAL, 'composite'),
        ('COVERING', 'covering range scan → 40 rows → no clustered row lookup', GREEN, 'covering'),
        ('REVERSED', 'optimizer chooses original run lookup → 462 rows → sort', ORANGE, 'reversed'),
    ]
    for i, (name, plan, color, key) in enumerate(rows):
        y = 168 + i * 134
        box(d, (68, y, 1530, y + 112))
        d.rectangle((69, y + 1, 82, y + 111), fill=color)
        text(d, 106, y + 13, name, 28, color, True)
        text(d, 106, y + 56, plan, 25, INK)
        ms = sixty[key]['median_ms']
        reads = sixty[key]['median_handler_reads']
        text(d, 1292, y + 12, f'{ms:.3f} ms', 28, color, True)
        text(d, 1300, y + 56, f'{reads} reads', 25, MUTED)
    ratio = sixty['baseline']['median_ms'] / sixty['covering']['median_ms']
    text(d, 72, 715, f'Covering versus baseline  {ratio:.2f}× faster;  463 → 41 Handler operations.', 29, NAVY, True)
    save(image, 'index_access.png')


def wide_cost():
    wide = benchmark['extensibility']
    image, d = canvas(545, 'A wide copy trades query work for maintenance',
                      'Equivalent participant-level reward aggregation · nine timed executions')
    pairs = [
        (70, 'Normalized tables', 'generic_joins', BLUE, 'joins at query time'),
        (820, 'Materialized wide copy', 'wide_materialized', TEAL, 'prejoined records'),
    ]
    for x, title, key, color, explanation in pairs:
        value = wide[key]
        box(d, (x, 176, x + 710, 405))
        d.rectangle((x + 1, 177, x + 13, 404), fill=color)
        text(d, x + 35, 194, title, 32, color, True)
        text(d, x + 35, 249, f'{value["median_ms"]:.2f} ms', 58, NAVY, True)
        text(d, x + 35, 327, f'{value["median_handler_reads"]:,} Handler operations', 27, INK)
        text(d, x + 35, 371, explanation, 24, MUTED)
    text(d, 72, 429, f'Wide copy refresh  {benchmark["wide_refresh_ms"]:.0f} ms', 28, ORANGE, True)
    text(d, 72, 474, 'It duplicates attributes. The normalized tables remain the canonical database.', 27, INK, True)
    save(image, 'wide_cost.png')


def validation_gate():
    checks = validation['checks']
    passed = sum(bool(value) for value in checks.values())
    assert len(checks) == 17 and passed == 17
    image, d = canvas(445, 'Final validation gate',
                      'Saved verification report · rerun the notebook cell below for the current database')
    text(d, 75, 161, '17 / 17', 58, GREEN, True)
    text(d, 365, 176, 'checks passed', 42, NAVY, True)
    for i in range(17):
        x = 80 + (i % 9) * 150
        y = 257 + (i // 9) * 62
        d.ellipse((x, y, x + 27, y + 27), fill=GREEN)
        d.line((x + 6, y + 14, x + 11, y + 19, x + 21, y + 8), fill='white', width=3)
    text(d, 75, 386, 'Sources · relationships · missing responses · model ownership · independent Q1 check', 25, MUTED)
    save(image, 'validation_gate.png')


if __name__ == '__main__':
    core_erd()
    model_erd()
    supporting_erd()
    trial_timeline()
    run_crosswalk()
    q1_adjacency()
    q3_window()
    event_patterns()
    provenance()
    index_access()
    wide_cost()
    validation_gate()
