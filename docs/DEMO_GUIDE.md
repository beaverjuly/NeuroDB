# Classroom demo guide

Present from the notebook. Switch to **Launch NeuroDB Explorer.command** only for live Q1 and Q3, then return to the notebook for the saved Q4 and Q8 outputs and benchmark evidence. The explorer places results above the SQL and keeps the matching logic diagram beside the query on wide screens. The notebook retains the core schema, integrity and physical design figures.

The sequence below follows the six minute presentation script and leaves time for questions within a 10 minute slot.

## Before class

* Launch NeuroDB and run every notebook cell before class. Confirm all 17 validation checks pass.
* Return to the top of the notebook.
* Open the separate explorer with its default participant, run and 0–60 second window.
* Open `results/NeuroDB_Demo.html` as a backup tab.
* Rehearse the window switch. Run only Q1 and Q3 live during the presentation.
* Keep `notebooks/SQL_Playground.ipynb` open in another JupyterLab tab for an unexpected question. The explorer's Custom SQL section offers the same read only path.

## Demonstration sequence

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:50 | Trial timeline, acquisition and run crosswalk | Separate behavioral and timing files need a checked run mapping |
| 0:50–1:30 | Core ERD, glance at model and provenance panels, then row counts | Point to PK and FK badges, one to many links, and the optional trial detail |
| 1:30–2:30 | Browser explorer with Q1 and Q3 | Execute Q1 and Q3 live; point to the visible SQL and matching diagrams |
| 2:30–3:05 | Q4 event patterns and Q8 extraction | Show saved outputs; missed trials have three expected events and absent model values stay NULL |
| 3:05–4:30 | Index plan graphic and saved plans | Baseline 462 to 40 with sort; composite 40 range rows; compare 60 second timings |
| 4:30–5:35 | Selectivity plots and wide cost graphic | Index value changes with window size; wide copy trades query work for refresh and duplication |
| 5:35–6:00 | Validation gate and check table | Confirm all 17 checks and state the project scope |

Use Q2, Q5 and Q6 if time permits or when asked. Explain the scientific question before displaying SQL.

If asked for a new query, open Custom SQL in the explorer or the SQL Playground tab. Start with `trial_context` for behavioral questions. The editor accepts SELECT, WITH, EXPLAIN SELECT, SHOW and DESCRIBE, shows at most 200 rows, and stops a query after five seconds. Use its prepared examples for run counts, missed responses, response time, event types, model coverage and schema inspection.

## Suggested opening

NeuroDB addresses a data management problem in computational neuroscience. A single trial can be represented across behavioral files, scanner timing files and model outputs. I built a MySQL database that links those records, validates the links and lets a researcher retrieve a trial or an event window with its source provenance. The database also lets me test whether the extra joins in a reusable schema affect query execution.

## What to say about query processing

| Observation | Interpretation |
| --- | --- |
| Baseline retains several indexes | InnoDB needs indexes for foreign keys, and natural keys add others; this is not an unindexed baseline |
| Composite run/onset access | Equality on the first column narrows to a run, followed by a range on onset |
| Covering access | The needed columns can be read from the index, if the selected plan shows that behavior |
| Reversed onset/run order | A leading range may require examining events from other runs before applying run equality |
| Explicit sort in a plan | MySQL did not obtain the full requested order directly from that access path |
| Similar warm timings | This dataset may fit in memory, and result transfer can dominate; rows and Handler operations remain useful evidence |
| Wide query is faster | Materialization trades joins at query time for duplicated attributes and refresh work |

Read the actual plans before claiming a particular operator was used. The benchmark does not force a preferred answer or synthesize extra research observations. Handler counts are not disk I/O measurements. A sort operator alone does not establish that a sort spilled to disk.

## Questions to prepare for

| Question | Answer |
| --- | --- |
| Why MySQL | The records have explicit relationships, integrity requirements and a join-heavy workload |
| Why a separate detail table | It keeps the core usable for other tasks without requiring every trial to have spaceship or planet fields |
| How would AX CPT fit | Cue, probe and response become event types; AX/AY/BX/BY belongs in an AX CPT detail extension; no second study is ingested here |
| Why no MongoDB | This is the proposal's individual-project MySQL scope; NoSQL is optional for a solo project |
| Why not infer missing outcomes | Preassigned source fields on missed trials are not observed outcomes; raw files remain available for inspection |
| Why distinguish 189 and 179 | The source scan cohort and the paper analytic cohort are different; undocumented inclusion is left unknown |
| Are these new neuroscience results | No. The contribution is validated database design and query processing |
| Are model fits available for everyone | Many author fit files exist, but only the independently validated pilot replay is loaded here |
| How is ingestion idempotent | Natural keys select existing rows and upserts preserve their identity; each attempt gets a separate audit record |
| What is the wide table cost | Duplicate attributes, refresh time and maintenance; physical allocation is measured in an isolated copy and includes page slack |

## If something fails during class

Rerun the startup cell if the database was stopped. If the explorer tab is closed, reopen **Launch NeuroDB Explorer.command**. If internet access is unavailable, the demo still works from the frozen local data and running MySQL instance. The HTML file is a reference for previously executed outputs and must be described as saved evidence, not a live query.
