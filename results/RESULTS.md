# Measured demo results

MySQL 8.4.11. Measurements recorded on November 21, 2026 at 08 55 PM PST. All observations are real public-source records.

| Database content | Exact count |
| --- | --- |
| participants | 189 |
| runs | 567 |
| trials | 48,951 |
| events | 172,854 |
| latent values | 3,870 |
| parameter estimates | 12 |

All 189 source participants passed the implemented alignment and database checks. This does not identify the paper's 179-person analytic sample. Latent values and parameters cover only the validated pilot.

## Event window experiment

The same 60-second interval returns 40 events. The baseline visits all 462 events in the run and sorts the selected rows. The composite index uses a run equality followed by an onset range and supplies the requested ordering. The reversed index is available, but the optimizer chooses the existing run-leading index for this query.

| Design | Median ms | Handler reads |
| --- | --- | --- |
| baseline | 0.813 | 463 |
| composite | 0.355 | 41 |
| covering | 0.324 | 41 |
| reversed | 0.789 | 463 |

Nine warm measurements follow two warm-up executions. Configurations are interleaved. Timing includes client execution and result fetching. Handler counts are not physical disk reads. At 720 seconds the whole run is retrieved, and the index alternatives have similar operation counts.

## Extensibility experiment

| Representation | Median ms | Handler reads |
| --- | --- | --- |
| Generic core and detail joins | 66.625 | 88,023 |
| Materialized wide copy | 35.082 | 29,107 |

Both return the same 378 participant and reward-condition aggregates. Building and indexing the temporary wide copy took 527.9 ms in this run. A matching isolated physical copy allocated 6.52 MiB of data pages and 2.52 MiB of index pages. The physical copy was removed after measurement.

The wide copy reduces query-time joins, but duplicates participant/run attributes and requires refreshing. It is an experiment, not the canonical source of observations. These are local warm measurements on this dataset, not general performance guarantees.

## Verification

All 17 database gates passed. Full reload equality passed for 17 canonical tables using exact counts and MySQL checksums. All 14 notebook code cells executed without errors. Integration test results are saved in `tests.log`.

Detailed evidence is in `benchmark.json`, `benchmark_summary.tsv`, `validation.json` and `idempotence.json`.
