"""Small live Jupyter interface. Every displayed query result comes from MySQL."""
import html
import ipywidgets as w
from IPython.display import display,HTML,Markdown,clear_output
from . import ROOT
from .queries import QUERIES,execute,defaults,query

def explorer():
    participants=query("SELECT bids_label FROM participants WHERE inclusion_status='validated' ORDER BY bids_label").bids_label.tolist()
    runs=query("SELECT p.bids_label,r.run_number,r.run_id FROM participants p JOIN sessions s USING(participant_id) JOIN runs r USING(session_id) WHERE r.run_type='functional' ORDER BY p.bids_label,r.run_number")
    select=w.Dropdown(options=[(k+'  '+v.title,k) for k,v in QUERIES.items()],description='Query',layout=w.Layout(width='600px'))
    participant=w.Dropdown(options=[('All validated participants',None)]+[(p,p) for p in participants],description='Participant',layout=w.Layout(width='440px'))
    condition=w.Dropdown(options=[('All',None),('Source code 1',1),('Source code 2',2)],description='Reward code')
    run=w.Dropdown(description='Run',layout=w.Layout(width='440px'))
    start=w.FloatText(value=0,description='Start seconds')
    end=w.FloatText(value=60,description='End seconds')
    variable=w.Dropdown(options=['spe_planet','mf_value_chosen','mb_value_chosen','mf_rpe_outcome','mb_rpe_outcome'],description='Variable',layout=w.Layout(width='440px'))
    plans=w.Checkbox(value=False,description='Show executed query plan')
    sql=w.Checkbox(value=False,description='Show SQL and bound parameters')
    button=w.Button(description='Run live query',button_style='primary',icon='play')
    output=w.Output();note=w.HTML()
    def refresh_runs(change=None):
        subset=runs if participant.value is None else runs[runs.bids_label==participant.value]
        options=[(f'{r.bids_label}  functional run {r.run_number}',r.run_id) for r in subset.itertuples()]
        run.options=options
        pilot=defaults()['run_id']
        if participant.value is None and pilot in [v for _,v in options]:run.value=pilot
    def refresh_query(change=None):
        q=select.value
        run.disabled=q not in ['Q3','Q8'];start.disabled=run.disabled;end.disabled=run.disabled
        variable.disabled=q!='Q8';condition.disabled=q in ['Q3','Q7']
        note.value='<p><b>'+html.escape(QUERIES[q].question)+'</b></p><p>'+html.escape(QUERIES[q].note)+'</p>'
    def run_query(_):
        with output:
            clear_output(wait=True)
            p=dict(participant=participant.value,condition=condition.value,run_id=run.value,
                   start=start.value if not start.disabled else 0.,end=end.value if not end.disabled else 60.,variable=variable.value)
            try:
                q=select.value;result=execute(q,p)
                display(Markdown(f'**{len(result):,} result rows**'))
                display(result.head(100))
                path=ROOT/'results'/f'interactive_{q}.tsv';result.to_csv(path,sep='\t',index=False)
                display(Markdown(f'Complete result saved in `results/{path.name}`. Display limited to 100 rows.'))
                if sql.value:display(Markdown('```sql\n'+QUERIES[q].sql+'\n```\nBound parameters\n```python\n'+repr(p)+'\n```'))
                if plans.value:
                    plan=execute(q,p,explain=True).iloc[0,0]
                    display(HTML('<pre style="white-space:pre-wrap">'+html.escape(plan)+'</pre>'))
            except Exception as exc:
                display(Markdown('Query could not run. '+str(exc)))
    participant.observe(refresh_runs,names='value');select.observe(refresh_query,names='value')
    button.on_click(run_query);refresh_runs();refresh_query()
    display(w.VBox([select,note,w.HBox([participant,condition]),run,w.HBox([start,end]),variable,
                    w.HBox([sql,plans]),button,output]))
    return dict(query=select,participant=participant,condition=condition,run=run,start=start,end=end,variable=variable,button=button,output=output)
