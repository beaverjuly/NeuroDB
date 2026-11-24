"""Parameterized, scientifically bounded query workload for the live demo."""
from dataclasses import dataclass
from .server import connect

@dataclass(frozen=True)
class Query:
    title:str
    question:str
    sql:str
    note:str

FILTER='(%(participant)s IS NULL OR bids_label=%(participant)s) AND (%(condition)s IS NULL OR reward_condition=%(condition)s)'
QUERIES={
'Q1':Query('Stay behavior','How does staying depend on the immediately preceding outcome and transition?',f'''
WITH ordered AS (
 SELECT *, LAG(chosen_ship) OVER w AS prev_ship, LAG(reward) OVER w AS prev_reward,
 LAG(transition_type) OVER w AS prev_transition, LAG(response_valid) OVER w AS prev_valid
 FROM trial_context WHERE run_type='functional' AND (%(participant)s IS NULL OR bids_label=%(participant)s)
 WINDOW w AS (PARTITION BY participant_id,run_id ORDER BY trial_number)
)
SELECT prev_reward,prev_transition,COUNT(*) AS eligible_pairs,
 SUM(chosen_ship=prev_ship) AS stay_count,AVG(chosen_ship=prev_ship) AS stay_probability
FROM ordered WHERE response_valid=1 AND prev_valid=1
 AND (%(condition)s IS NULL OR reward_condition=%(condition)s)
GROUP BY prev_reward,prev_transition ORDER BY prev_reward,prev_transition
''','LAG precedes missed-trial and condition filtering. No pairs cross a run boundary or skip a missed response. Pooled eligible pairs are descriptive.'),
'Q2':Query('Reward by condition','How does reward rate vary by condition and task order after giving each participant equal weight?',f'''
WITH participant_rates AS (
 SELECT participant_id,design_variant,task_order,reward_condition,
 AVG(reward) AS reward_rate,COUNT(*) AS valid_trials
 FROM trial_context WHERE run_type='functional' AND response_valid=1 AND {FILTER}
 GROUP BY participant_id,design_variant,task_order,reward_condition
)
SELECT design_variant,task_order,reward_condition,COUNT(*) AS participants,
 SUM(valid_trials) AS valid_trials,AVG(reward_rate) AS mean_participant_reward_rate,
 STDDEV_SAMP(reward_rate) AS participant_sd
FROM participant_rates GROUP BY design_variant,task_order,reward_condition
ORDER BY design_variant,task_order,reward_condition
''','Conditions retain the source numeric codes. Task order is an observed grouping; published model clusters are unavailable. State-only participants remain separately labeled.'),
'Q3':Query('Event window','Which events occurred during this interval of a functional run?','''
SELECT e.event_id,e.trial_id,t.trial_number,et.event_name,e.onset_seconds,e.duration_seconds
FROM events e JOIN event_types et USING(event_type_id) LEFT JOIN trials t ON t.trial_id=e.trial_id
WHERE e.run_id=%(run_id)s AND e.onset_seconds >= %(start)s AND e.onset_seconds < %(end)s
ORDER BY e.onset_seconds,e.event_id
''','Half-open interval in seconds relative to scanner run start. The time-window experiment uses the same access pattern.'),
'Q4':Query('Event integrity','Do completed and missed trials have their expected event types?',f'''
WITH counts AS (
 SELECT tc.bids_label,tc.run_id,tc.run_number,tc.trial_id,tc.trial_number,tc.response_valid,
 COUNT(e.event_id) AS observed_events,
 SUM(et.event_name='fixation') AS n_fixation,SUM(et.event_name='stimulus') AS n_stimulus,
 SUM(et.event_name IN ('response_left','response_right')) AS n_response,
 SUM(et.event_name='response_missing') AS n_missing,
 SUM(et.event_name='planet') AS n_planet,SUM(et.event_name='pad') AS n_pad,SUM(et.event_name='outcome') AS n_outcome
 FROM trial_context tc LEFT JOIN events e ON e.trial_id=tc.trial_id LEFT JOIN event_types et USING(event_type_id)
 WHERE tc.run_type='functional' AND {FILTER}
 GROUP BY tc.bids_label,tc.run_id,tc.run_number,tc.trial_id,tc.trial_number,tc.response_valid
), classified AS (
 SELECT *,IF(response_valid,6,3) AS expected_events,
 CASE WHEN n_fixation=1 AND n_stimulus=1 AND
 ((response_valid=1 AND n_response=1 AND n_missing=0 AND n_planet=1 AND n_pad=1 AND n_outcome=1 AND observed_events=6)
 OR (response_valid=0 AND n_response=0 AND n_missing=1 AND n_planet=0 AND n_pad=0 AND n_outcome=0 AND observed_events=3))
 THEN 'expected' ELSE 'unexpected' END AS event_pattern
 FROM counts
)
SELECT response_valid,event_pattern,COUNT(*) AS trials,SUM(observed_events) AS observed_events,
 SUM(expected_events) AS expected_events FROM classified
GROUP BY response_valid,event_pattern ORDER BY response_valid,event_pattern
''','Six events per completed trial, three per missed trial. Structural trials have no timing input and are excluded from this audit.'),
'Q5':Query('Transition and SPE','Within the validated pilot, how does stage-one state prediction error differ for rare and common transitions?',f'''
SELECT tc.bids_label,tc.transition_type,COUNT(*) AS trials,AVG(lv.value) AS mean_stage_one_spe
FROM trial_context tc JOIN latent_values lv USING(trial_id) JOIN variable_definitions vd USING(variable_id)
JOIN participant_fits pf USING(fit_id) JOIN fitting_jobs fj ON fj.job_id=pf.job_id AND fj.model_id=vd.model_id
JOIN events e ON e.trial_id=tc.trial_id AND e.event_type_id=vd.locking_event_type_id
WHERE tc.run_type='functional' AND vd.variable_name='spe_planet' AND {FILTER}
GROUP BY tc.bids_label,tc.transition_type ORDER BY tc.bids_label,tc.transition_type
''','Pilot extension only. Stage-one SPE reflects the fixed transition model; this is a consistency check, not an independent scientific discovery.'),
'Q6':Query('MB and MF conflict','How often do MB and MF utilities prefer opposite actions within the validated pilot?',f'''
WITH utilities AS (
 SELECT tc.bids_label,tc.trial_id,lv.fit_id,
 MAX(CASE WHEN vd.variable_name='mf_value_chosen' THEN lv.value END)-MAX(CASE WHEN vd.variable_name='mf_value_rejected' THEN lv.value END) AS mf_delta,
 MAX(CASE WHEN vd.variable_name='mb_value_chosen' THEN lv.value END)-MAX(CASE WHEN vd.variable_name='mb_value_rejected' THEN lv.value END) AS mb_delta
 FROM trial_context tc JOIN latent_values lv USING(trial_id) JOIN variable_definitions vd USING(variable_id)
 WHERE tc.run_type='functional' AND {FILTER}
 GROUP BY tc.bids_label,tc.trial_id,lv.fit_id
)
SELECT bids_label,fit_id,COUNT(*) AS comparable_trials,SUM(mf_delta*mb_delta<0) AS opposite_sign_trials,
 SUM(mf_delta=0 OR mb_delta=0) AS trials_with_ties,AVG(mf_delta*mb_delta<0) AS conflict_fraction
FROM utilities WHERE mf_delta IS NOT NULL AND mb_delta IS NOT NULL GROUP BY bids_label,fit_id
''','Compare signs of within-system chosen-minus-rejected utilities. MB and MF values are never subtracted from each other.'),
'Q7':Query('Participant audit','Which source participants loaded successfully, and what coverage is available?','''
SELECT p.bids_label,p.design_variant,p.inclusion_status,p.analytic_inclusion_status,p.exclusion_reason,
 COUNT(DISTINCT r.run_id) AS runs,COUNT(t.trial_id) AS behavior_trials,
 COALESCE(SUM(r.run_type='functional'),0) AS functional_trials,
 COALESCE(SUM(t.response_valid=0),0) AS missed_trials,p.metadata_note
FROM participants p LEFT JOIN sessions s USING(participant_id) LEFT JOIN runs r USING(session_id)
LEFT JOIN trials t USING(run_id) WHERE (%(participant)s IS NULL OR p.bids_label=%(participant)s)
GROUP BY p.participant_id ORDER BY p.bids_label
''','Source cohort, validated database cohort, and paper analytic cohort are distinct. Analytic inclusion remains unknown unless documented for that identity.'),
'Q8':Query('Analysis extraction','Can we retrieve ordered event records, selected modulators and their provenance?',f'''
SELECT tc.bids_label,tc.run_number,tc.behavior_run_number,tc.trial_number,tc.response_valid,
 et.event_name,e.onset_seconds,e.duration_seconds,tc.chosen_ship,tc.reward,
 vd.variable_name,lv.value AS modulator,pf.fit_id,ms.version AS model_version,
 obs.source_url AS behavior_source,obs.checksum AS behavior_sha256,
 timing.source_url AS timing_source,timing.checksum AS timing_sha256,
 fit_source.source_url AS fit_source
FROM trial_context tc JOIN events e USING(trial_id) JOIN event_types et USING(event_type_id)
JOIN source_files obs ON obs.source_file_id=tc.source_file_id
JOIN source_files timing ON timing.source_file_id=e.source_file_id
LEFT JOIN variable_definitions vd ON vd.variable_name=%(variable)s AND vd.locking_event_type_id=e.event_type_id
LEFT JOIN latent_values lv ON lv.trial_id=tc.trial_id AND lv.variable_id=vd.variable_id
LEFT JOIN participant_fits pf ON pf.fit_id=lv.fit_id
LEFT JOIN fitting_jobs fj ON fj.job_id=pf.job_id
LEFT JOIN model_specifications ms ON ms.model_id=fj.model_id
LEFT JOIN source_files fit_source ON fit_source.source_file_id=pf.source_file_id
WHERE tc.run_id=%(run_id)s AND {FILTER}
 AND e.onset_seconds >= %(start)s AND e.onset_seconds < %(end)s
ORDER BY tc.trial_number,e.onset_seconds,e.event_id
''','All observed events remain visible. A NULL modulator means unavailable at this event or participant; it is never replaced with zero.')
}

def defaults():
    with connect() as conn,conn.cursor() as c:
        c.execute("SELECT r.run_id FROM runs r JOIN sessions s USING(session_id) JOIN participants p USING(participant_id) WHERE p.bids_label='sub-MBMF001502' AND r.run_type='functional' AND r.run_number=1")
        run=c.fetchone()['run_id']
    return dict(participant=None,condition=None,run_id=run,start=0.,end=60.,variable='spe_planet')

def execute(query_id,params=None,explain=False):
    import pandas as pd
    if query_id not in QUERIES:raise ValueError('Unknown query')
    parameters=defaults() if params is None else params.copy()
    if not 0<=float(parameters['start'])<float(parameters['end']):raise ValueError('Use 0 <= start < end')
    sql=QUERIES[query_id].sql
    with connect() as conn,conn.cursor() as c:
        c.execute(('EXPLAIN ANALYZE ' if explain else '')+sql,parameters)
        rows=c.fetchall()
        return pd.DataFrame(rows,columns=[d[0] for d in c.description])

def query(sql,params=()):
    import pandas as pd
    with connect() as conn,conn.cursor() as c:
        c.execute(sql,params)
        return pd.DataFrame(c.fetchall(),columns=[d[0] for d in c.description])
