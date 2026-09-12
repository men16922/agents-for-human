from pathlib import Path
from dataclasses import replace
import argparse, json, os, time, random
from copy import deepcopy
from rehearsal.evaluation.frozen_run import condition_id
from rehearsal.agents.runner import read_settings, bedrock_model
from rehearsal.evaluation.batch import prepare, run_pending, summarize, rows
from rehearsal.evaluation.pilot import known_cases

root = Path.cwd()
base = root/'.local/nova-live-20260912'
parser=argparse.ArgumentParser()
parser.add_argument('id')
args=parser.parse_args()
assert args.id.replace('-','').isalnum()
os.umask(0o077)
for line in (base/'nova.env').read_text().splitlines():
    key,value=line.split('=',1)
    os.environ[key]=value
settings=replace(read_settings(root),budget_micro_usd=500000,input_limit=16000,
                 max_model_calls=64,max_tool_calls=80,max_total_tokens=300000)
directory=base/args.id
training=json.loads((root/'scenarios/normal-v1.json').read_text())
training['scenario_version']='nova-pilot-training-a61-v1'
training['suppliers']['A']['items']['tent']['price']=61
rng=random.Random(2026091201)
cases={}
normal=json.loads((root/'scenarios/normal-v1.json').read_text())
for family in ['price','stock','lead','partial','impossible']:
    for repeat in range(4):
        case=deepcopy(normal)
        case['scenario_version']=f'prospective-{family}-{repeat+1}-v1'
        for name,supplier in case['suppliers'].items():
            supplier['shipping']=rng.randint(5,24)
            supplier['items']['tent']['price']=rng.randint(43,96)
            supplier['items']['light']['price']=rng.randint(12,33)
            if family=='stock':
                supplier['items']['tent']['stock']=rng.randint(0,6)
                supplier['items']['light']['stock']=rng.randint(0,9)
            if family=='lead':
                supplier['lead_ticks']=rng.randint(6,42)
            if family=='partial':
                supplier['items']['tent']['stock']=0 if name!='A' else 3
                supplier['items']['light']['stock']=0 if name!='B' else 6
            if family=='impossible':
                supplier['items']['tent']['stock']=0
        cases[f'{family}-{repeat+1}']=case
prior={condition_id(c) for c in known_cases(root).values()}
assert not prior.intersection({condition_id(c) for c in cases.values()})
manifest=prepare(directory,training,cases,1,settings,4000000,'live-model')
protocol={'scope':'prospective-new-condition-evaluation','generated_before_any_batch_call':True,'seed':2026091201,'families':['price','stock','lead','partial','impossible'],'conditions_per_family':4,'repeats_per_condition':1,'planned_cells':80,'training_condition_id':condition_id(training),'evaluation_condition_ids':{k:condition_id(v) for k,v in cases.items()},'prior_pilot_overlap':False,'frozen_before_execution':manifest['id'],'tuning_during_batch':False,'learning_repeated_independently_per_cell':True,'independent_external_heldout_audit':False,'limitations':['Known fault families; new parameter combinations','One execution per condition per arm; no statistical superiority claim','Original conservative held_out=false runner classification retained']}
(directory/'prospective-protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
path=base/'campaign.json'
campaign=json.loads(path.read_text())
assert not any(e['reserved_micro_usd'] for e in campaign['entries'])
assert not any(e['id']==args.id for e in campaign['entries'])
assert sum(e['recorded_micro_usd'] for e in campaign['entries'])+4000000 <= campaign['admission_limit_micro_usd']
entry={'id':args.id,'stage':'twenty-prospective-conditions-four-arms','scope':'live-model',
       'directory':str(directory),'status':'ADMITTED','recorded_micro_usd':0,
       'reserved_micro_usd':4000000,'planned_cells':80}
campaign['entries'].append(entry)
path.write_text(json.dumps(campaign,indent=2)+'\n')
start=time.perf_counter()
try:
    for number in range(80):
        report=run_pending(directory,lambda kind,policy:bedrock_model(settings),max_cells=1)
        finished=[c for c in report['cells'] if c['status'] not in {'NOT_RUN','RUNNING'}]
        print(json.dumps({'finished':len(finished),'last':{k:finished[-1].get(k) for k in ['id','method','status','goal_complete','spent']} if finished else None,
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
