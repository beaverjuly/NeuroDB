# Data dictionary and decisions

## Identity and run mapping

| Field | Meaning |
| --- | --- |
| `source_person_id` | Four digit person identifier preserved from the public sources |
| `bids_label` | Original OpenNeuro label, verified against the frozen 1.0.5 tree |
| `task_order` | The timing MAT session/order identifier, verified against the BIDS suffix |
| Behavioral filename | Preserved whole; its s/f suffix is not used to infer task order |
| `behavior_run_number` | Original behavioral `runID` |
| `run_type` | Original `sess_type`, either structural or functional |
| `run_number` | Within-type run number, with functional 1 and 2 matched to timing runs |
| `trial_number` | Within-run sequence beginning at one |
| `source_trial_number` | Original source trial identifier; functional IDs span 1 through 154 |
| `source_row_number` | One-based CSV row index excluding the header |

Two source run orders occur. Some participants have structural run 1 and functional runs 2 and 3. Others have functional runs 1 and 2 and structural run 3. The mapping is derived from the observed session labels and checked against MATLAB trials. Neither mapping is imposed on every participant.

## Observations

| Database attribute | Source and transformation |
| --- | --- |
| `response_valid` | `Resp1` is present and has an allowed choice code |
| `chosen_ship` | Behavioral `Resp1`, action code 1 or 2 |
| `visited_planet` | Behavioral `outcome1` on valid trials |
| `visited_pad` | Behavioral `outcome2`, crosschecked against timing `outcome1` |
| `reward` | Behavioral binary `outcomeBin` on valid trials |
| `reward_magnitude` | Behavioral `outcomeMag` in its source units, not the separate `rewMagnitude` field |
| `transition_type` | `doRareTrans` becomes common or rare on observed trials |
| `reward_condition` | Original numeric `condReward` code |
| `contingency_condition` | Original numeric `condContingent` code |
| `state_condition` | Original numeric `condState` code |
| `response_time` | Original `RT1`, including timeout duration on missed trials |

Source condition codes are retained without assigning unverified semantic labels. A missed response leaves chosen action, visited states, reward and observed transition missing. Original preassigned fields are retained in the checksummed CSV, not reinterpreted as observed outcomes.

## Events

| Event | MATLAB timestamp | Rule |
| --- | --- | --- |
| fixation | `tStart` | Every trial; the source task leaves `tFixOn` empty |
| stimulus | `tStim1On` | Every trial |
| response_left or response_right | `tResp1` | Completed response |
| response_missing | `tResp1` | Timeout marker, not an observed button response |
| planet | `tState2On` | Completed trial |
| pad | `tTerminalState2On` | Completed trial |
| outcome | `tFBOn_Bin` | Completed trial, checked against `tFBOn_Mag` |

Onsets subtract the corresponding `tRunStart`. Timing equality and run bounds use a 1e-6 second tolerance. Behavior/timing reaction-time alignment uses the tighter tolerance preserved in the pilot wrapper. Duration zero represents a stick-event convention, not a measured stimulus duration. Structural trial timing is unavailable and is not manufactured. TR and scan count are retained only for the pilot where they were previously verified; other runs have NULL acquisition values.

## Integrity

Primary and natural unique keys make loading repeatable. The event composite foreign key uses `(run_id, trial_id)` and targets the corresponding unique trial key. A generated event scope key converts NULL trial references to a reserved zero for uniqueness, so run-level events cannot silently duplicate through MySQL's NULL uniqueness behavior.

Participant-fit versus trial ownership and model-fit versus variable-definition consistency are cross-table checks in the validation program. They are not misrepresented as MySQL CHECK constraints. Parameter names are also checked against the fitting model's parameter definitions. This prototype's importer is the supported writer; direct SQL writes to model tables must be followed by validation.

## Inclusion and provenance

`inclusion_status` describes database ingestion. `analytic_inclusion_status` remains unknown because no complete person-level analytic crosswalk is established here. The five state-only participants and the incomplete fieldmap note come from the pinned OpenNeuro README. A study-wide scanned count is never used as an observed SQL row count.

Source files retain their URL, version or commit reference, checksum, availability and license status. Each ingestion records a transformation version, a code checksum, execution time and per-source validation status. `rows_loaded` counts accepted logical input observations associated with that source, not newly inserted rows; it may repeat on an idempotent reload.

## Model extension

The pilot uses the released 12-parameter author fit and the previously validated deterministic replay. Its objective is log joint density, not data log likelihood alone. Parameters retain raw and applied or interpretable baseline values with transformation definitions.

Decision utilities lock to the stimulus event. Planet, pad and outcome prediction errors lock to their corresponding stage. No latent is loaded for a missed response. Q5 checks a fixed-transition model implication. Q6 compares the signs of chosen-minus-rejected utility within each system, avoiding subtraction between incompatible MB and MF scales.

The wide experiment materializes the behavioral core plus the task detail extension, as specified by the primary physical-design experiment. It does not benchmark an EAV-to-wide latent pivot. Such a model-specific extension would need a separately defined workload.
