from pathlib import Path
from dataclasses import replace
import json, os, time
from rehearsal.agents.runner import read_settings, bedrock_model
from rehearsal.evaluation.batch import prepare, run_pending, summarize, rows
from rehearsal.evaluation.pilot import known_cases

root = Path.cwd()
base = root/'.local/nova-live-20260912'
os.umask(0o077)
for line in (base/'nova.env').read_text().splitlines():
    key,value=line.split('=',1)
    os.environ[key]=value
settings=replace(read_settings(root),budget_micro_usd=500000,input_limit=16000,
                 max_model_calls=64,max_tool_calls=80,max_total_tokens=300000)
directory=base/'pilot-01'
training=json.loads((root/'scenarios/normal-v1.json').read_text())
training['scenario_version']='nova-pilot-training-a61-v1'
training['suppliers']['A']['items']['tent']['price']=61
manifest=prepare(directory,training,known_cases(root),1,settings,2000000,'live-model')
path=base/'campaign.json'
campaign=json.loads(path.read_text())
assert not any(e['reserved_micro_usd'] for e in campaign['entries'])
assert not any(e['id']=='pilot-01' for e in campaign['entries'])
assert sum(e['recorded_micro_usd'] for e in campaign['entries'])+2000000 <= campaign['admission_limit_micro_usd']
entry={'id':'pilot-01','stage':'five-known-conditions-four-arms','scope':'live-model',
       'directory':str(directory),'status':'ADMITTED','recorded_micro_usd':0,
       'reserved_micro_usd':2000000,'planned_cells':20}
campaign['entries'].append(entry)
path.write_text(json.dumps(campaign,indent=2)+'\n')
start=time.perf_counter()
try:
    for number in range(20):
        report=run_pending(directory,lambda kind,policy:bedrock_model(settings),max_cells=1)
        finished=[c for c in report['cells'] if c['status'] not in {'NOT_RUN','RUNNING'}]
        print(json.dumps({'finished':len(finished),'last':{k:finished[-1].get(k) for k in ['cell_id','method','status','goal_complete','spent']} if finished else None,
                          'cost_micro_usd':report['recorded_micro_usd'],'reserved':report['unresolved_reserved_micro_usd'],'stop':report.get('stop_reason')}),flush=True)
        if report.get('stop_reason') not in {None,'CELL_LIMIT'} or report['unresolved_reserved_micro_usd']:
            break
finally:
    report=summarize(directory)
    (directory/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    entry.update(recorded_micro_usd=report['recorded_micro_usd'],elapsed_seconds=time.perf_counter()-start,
                 status='FINISHED' if report['all_cells_resolved'] else 'PARTIAL')
    if report['unresolved_reserved_micro_usd']==0 and not any(c['status']=='RUNNING' for c in report['cells']):
        entry['reserved_micro_usd']=0
    else:
        entry['status']='USAGE_UNRESOLVED'
    path.write_text(json.dumps(campaign,indent=2)+'\n')
    print(json.dumps({'entry':entry,'methods':report['methods'],'status_counts':report['status_counts']},indent=2),flush=True)
