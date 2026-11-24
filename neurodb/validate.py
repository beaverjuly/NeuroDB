"""Machine-readable audit of database relationships, sources and query outputs."""
from datetime import datetime, timezone
import json
import pandas as pd
from . import ROOT
from .acquire import digest
from .server import connect
from .queries import QUERIES, execute, defaults, query

def validate(save=True):
    checks={}
    with connect() as conn,conn.cursor() as c:
        def scalar(sql,args=()):
            c.execute(sql,args);return next(iter(c.fetchone().values()))
        tables=['participants','sessions','runs','trials','two_step_trial_details','events','source_files','latent_values','parameter_estimates']
        counts={t:scalar('SELECT COUNT(*) FROM '+t) for t in tables}
        checks['mysql_84']=str(scalar('SELECT VERSION()')).startswith('8.4.')
        checks['minimum_30_validated']=scalar("SELECT COUNT(*) FROM participants WHERE inclusion_status='validated'")>=30
        checks['one_detail_per_trial']=counts['trials']==counts['two_step_trial_details']
        checks['event_run_consistency']=scalar('SELECT COUNT(*) FROM events e JOIN trials t USING(trial_id) WHERE e.run_id<>t.run_id')==0
        checks['events_within_task_run']=scalar('SELECT COUNT(*) FROM events e JOIN runs r USING(run_id) WHERE e.onset_seconds < -0.000001 OR e.onset_seconds > r.run_duration+0.000001 OR r.run_duration IS NULL')==0
        checks['fit_trial_participant_consistency']=scalar('SELECT COUNT(*) FROM latent_values lv JOIN participant_fits pf USING(fit_id) JOIN trials t USING(trial_id) JOIN runs r USING(run_id) JOIN sessions s USING(session_id) WHERE pf.participant_id<>s.participant_id')==0
        checks['fit_variable_model_consistency']=scalar('SELECT COUNT(*) FROM latent_values lv JOIN variable_definitions vd USING(variable_id) JOIN participant_fits pf USING(fit_id) JOIN fitting_jobs fj USING(job_id) WHERE vd.model_id<>fj.model_id')==0
        checks['parameter_definition_consistency']=scalar('SELECT COUNT(*) FROM parameter_estimates pe JOIN participant_fits pf USING(fit_id) JOIN fitting_jobs fj USING(job_id) LEFT JOIN parameter_definitions pd ON pd.model_id=fj.model_id AND pd.parameter_name=pe.parameter_name WHERE pd.parameter_name IS NULL')==0
        checks['no_latents_on_missed_trials']=scalar('SELECT COUNT(*) FROM latent_values lv JOIN trials t USING(trial_id) WHERE t.response_valid=0')==0
        checks['no_imputed_missed_outcomes']=scalar('SELECT COUNT(*) FROM two_step_trial_details d JOIN trials t USING(trial_id) WHERE t.response_valid=0 AND (d.reward IS NOT NULL OR d.visited_planet IS NOT NULL OR d.visited_pad IS NOT NULL)')==0
        checks['excluded_participants_have_no_trials']=scalar("SELECT COUNT(*) FROM trial_context tc JOIN participants p USING(participant_id) WHERE p.inclusion_status<>'validated'")==0
        checks['latest_ingestion_passed']=scalar('SELECT status FROM ingestion_runs ORDER BY ingestion_id DESC LIMIT 1')=='passed'
        c.execute('SELECT local_path,checksum FROM source_files WHERE available_on_disk=1')
        bad_sources=[r['local_path'] for r in c.fetchall() if not (ROOT/r['local_path']).is_file() or digest(ROOT/r['local_path'])!=r['checksum']]
        checks['source_checksums']=not bad_sources
        c.execute("SELECT p.bids_label,COUNT(t.trial_id) AS trials FROM participants p JOIN sessions s USING(participant_id) JOIN runs r USING(session_id) JOIN trials t USING(run_id) WHERE p.bids_label='sub-MBMF001502' GROUP BY p.bids_label")
        pilot=c.fetchone();checks['pilot_259_trials']=pilot is not None and pilot['trials']==259
        checks['pilot_921_events']=scalar("SELECT COUNT(*) FROM events e JOIN runs r USING(run_id) JOIN sessions s USING(session_id) JOIN participants p USING(participant_id) WHERE p.bids_label='sub-MBMF001502'")==921
        mysql_version=scalar('SELECT VERSION()')
        c.execute('SELECT inclusion_status,COUNT(*) AS participants FROM participants GROUP BY inclusion_status');cohort=c.fetchall()
    query_results={}
    for qid in QUERIES:
        frame=execute(qid);query_results[qid]={'returned_rows':len(frame),'executed':True}
        if save:frame.to_csv(ROOT/'results'/f'{qid}.tsv',sep='\t',index=False)
        if qid=='Q4':checks['expected_event_patterns']=set(frame.event_pattern)=={'expected'}
    # Independent Pandas reference for the LAG workload, including missed trials before shifting.
    behavior=query("SELECT participant_id,run_id,trial_number,response_valid,chosen_ship,reward,transition_type FROM trial_context WHERE run_type='functional' ORDER BY participant_id,run_id,trial_number")
    prev=behavior.groupby(['participant_id','run_id'])[['chosen_ship','reward','transition_type','response_valid']].shift(1)
    eligible=behavior.response_valid.eq(1)&prev.response_valid.eq(1)
    ref=pd.DataFrame({'prev_reward':prev.reward,'prev_transition':prev.transition_type,'stay':behavior.chosen_ship.eq(prev.chosen_ship)})[eligible]
    expected=ref.groupby(['prev_reward','prev_transition']).stay.agg(['size','sum'])
    actual=execute('Q1').set_index(['prev_reward','prev_transition'])
    checks['q1_independent_reference']=expected['size'].to_dict()==actual.eligible_pairs.to_dict() and expected['sum'].to_dict()==actual.stay_count.to_dict()
    result=dict(checked_at=datetime.now(timezone.utc).isoformat(),mysql_version=mysql_version,
        counts=counts,cohort=cohort,checks=checks,queries=query_results,bad_sources=bad_sources,passed=all(checks.values()))
    if save:(ROOT/'results/validation.json').write_text(json.dumps(result,indent=2,default=str))
    return result

if __name__=='__main__':
    result=validate();print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
