from pathlib import Path
from dataclasses import replace
import argparse,json,os,sys,threading,time
root=Path.cwd();base=root/'.local/nova-live-20260912';sys.path.insert(0,str(root/'scripts/commerce'))
from model_session import Session
from reaction_smoke import RecordedClient
from rehearsal.agents.runner import read_settings,bedrock_model
from rehearsal.commerce.model_runner import execute_http,attest,digest,write
from rehearsal.commerce.reaction import ReactionSettings
from rehearsal.evaluation.conditions import verify_conditions
from rehearsal.evaluation.condition_events import verify_events
from rehearsal.experiments.frozen import freeze
from rehearsal.experiments.policy import Policy
parser=argparse.ArgumentParser();parser.add_argument('id');parser.add_argument('--tick',type=int,default=4);args=parser.parse_args();assert args.id.replace('-','').isalnum()
os.umask(0o077)
for line in (base/'nova.env').read_text().splitlines():
 k,v=line.split('=',1);os.environ[k]=v
settings=replace(read_settings(root),budget_micro_usd=500000,max_model_calls=48,max_tool_calls=60,input_limit=24000,max_total_tokens=300000,timeout_seconds=120)
p=base/args.id;p.mkdir();case=json.loads((root/'scenarios/normal-v1.json').read_text());case['goal']['deadline_tick']=90;case['events']=[{'id':'stock','kind':'stock','at_tick':args.tick,'max_lateness_ticks':2,'supplier':'A','item':'tent','value':0}];write(p/'case.json',case);frozen=freeze(Policy(),p/'policy.json',root)
cp=base/'campaign.json';campaign=json.loads(cp.read_text());assert not any(e['reserved_micro_usd'] for e in campaign['entries']);assert sum(e['recorded_micro_usd'] for e in campaign['entries'])+settings.budget_micro_usd<=campaign['admission_limit_micro_usd'];assert not any(e['id']==args.id for e in campaign['entries'])
entry={'id':args.id,'scope':'live-model','stage':'Medusa-stock-reaction','directory':str(p),'status':'ADMITTED','recorded_micro_usd':0,'reserved_micro_usd':settings.budget_micro_usd};campaign['entries'].append(entry);write(cp,campaign)
session=Session(p/'policy.json',fixture=False,case=case);client=worker=None;stop=threading.Event();errors=[];result={};start=time.perf_counter()
try:
 sp=session.start();entry['session_directory']=str(sp);write(cp,campaign)
 def maintain():
  try: session.wait(stop)
  except Exception as exc: errors.append(type(exc).__name__)
 worker=threading.Thread(target=maintain);worker.start();config=json.loads((sp/'buyer-config.json').read_text());initial=json.loads((sp/session.record['conditions_path']).read_text());verified=verify_conditions(initial,case,config['run_id']);write(p/'conditions.json',initial);client=RecordedClient(config,p)
 result=execute_http(bedrock_model(settings),settings,client,p/'execution',config['expected_goal'],config['expected_budget'],frozen,'live-model',initial_condition={'sha256':digest(p/'conditions.json'),'verification':verified},reaction_settings=ReactionSettings(16))
 entry['runtime_status']=result['runtime_status']
finally:
 stop.set()
 if worker: worker.join(15)
 session.close('NOVA_REACTION_FINISHED')
 if client: client.close()
 if (p/'execution/report.json').exists() and 'usage' in json.loads((p/'execution/report.json').read_text()):
  usage=json.loads((p/'execution/report.json').read_text())['usage'];entry['recorded_micro_usd']=usage['recorded_micro_usd']
  if usage['all_usage_recorded']:entry['reserved_micro_usd']=0
 entry.update(status='FINISHED' if entry['reserved_micro_usd']==0 else 'USAGE_UNRESOLVED',elapsed_seconds=time.perf_counter()-start);write(cp,campaign)
 report={'entry':entry,'session':session.record,'worker_errors':errors,'runtime':result,'model_efficacy_verified':False}
 if session.path and (session.path/'selection.json').exists() and (p/'execution/execution-manifest.json').exists():
  report['attestation']=attest(p/'execution',session.path/'selection.json');ev=json.loads((session.path/'evidence.json').read_text());report['events']=verify_events(ev['condition_events'],case,ev['binding'],verified['capture_end_tick'],ev['captured_at_tick'])
 write(p/'result.json',report);print(json.dumps({'entry':entry,'attestation':report.get('attestation',{}).get('success'),'events':report.get('events'),'reactions':result.get('reactions'),'worker_errors':errors},indent=2))
