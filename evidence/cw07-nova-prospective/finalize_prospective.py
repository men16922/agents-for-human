from pathlib import Path
import hashlib,json,shutil,sqlite3
from decimal import Decimal,ROUND_CEILING
from rehearsal.evaluation.batch import summarize
from rehearsal.evaluation.metrics import report,markdown
from rehearsal.evaluation.frozen_run import condition_id
root=Path.cwd();base=root/'.local/nova-live-20260912';source=base/'prospective-01';campaign=json.loads((base/'campaign.json').read_text());entry=next(x for x in campaign['entries'] if x['id']=='prospective-01');assert entry['status']=='FINISHED' and entry['reserved_micro_usd']==0
original=summarize(source);assert original['all_cells_resolved'] and original['planned']==80 and 'INVALID_EVIDENCE' not in original['status_counts']
target=root/'evidence/cw07-nova-prospective';target.mkdir(exist_ok=False);shutil.copytree(source,target/'batch');audited=summarize(target/'batch');assert audited==original
(target/'copy-reaudit.json').write_text(json.dumps(audited,indent=2)+'\n');metrics=report(target/'batch');(target/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n');(target/'metrics.md').write_text(markdown(metrics))
for name in ['campaign.json','run_prospective.py','prospective-01.log','finalize_prospective.py']:shutil.copy2(base/name,target/name)
manifest=json.loads((source/'manifest.json').read_text());assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==value for name,value in manifest['source_hashes'].items())
for name in manifest['source_hashes']:
 dest=target/'executed-source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,dest)
previous=set()
for p in (root/'evidence').rglob('manifest.json'):
 if p.is_relative_to(target):continue
 try:d=json.loads(p.read_text());cases=d.get('cases',{})
 except (ValueError,UnicodeError):continue
 if isinstance(cases,dict):previous.update(condition_id(c) for c in cases.values() if isinstance(c,dict))
current={condition_id(c) for c in manifest['cases'].values()};(target/'partition-audit.json').write_text(json.dumps({'new_conditions':len(current),'prior_retained_conditions_checked':len(previous),'overlap':sorted(current&previous),'training_overlap':condition_id(manifest['training']) in current,'source_hashes_current':True,'external_heldout_audit':False},indent=2)+'\n')
calls=total=0;tokens={};ledgers=[]
for p in base.rglob('usage.sqlite3'):
 db=sqlite3.connect(f'file:{p.resolve()}?mode=ro',uri=True);db.row_factory=sqlite3.Row;rates={r['run_id']:json.loads(r['rates']) for r in db.execute('select run_id,rates from model_runs')};amount=0
 for r in db.execute('select * from model_calls'):
  assert r['status']=='RECORDED';u=json.loads(r['usage']);cost=Decimal(0);calls+=1
  for k,rk in [('inputTokens','input_usd_per_million'),('outputTokens','output_usd_per_million'),('cacheReadInputTokens','cache_read_usd_per_million'),('cacheWriteInputTokens','cache_write_usd_per_million')]:
   tokens[k]=tokens.get(k,0)+u.get(k,0);cost+=u.get(k,0)*Decimal(rates[r['run_id']][rk])
  assert int(cost.to_integral_value(rounding=ROUND_CEILING))==r['estimated_micro_usd'];amount+=r['estimated_micro_usd']
 total+=amount;ledgers.append({'ledger':str(p.relative_to(base)),'recorded_micro_usd':amount})
assert total==sum(x['recorded_micro_usd'] for x in campaign['entries']);assert not any(x['reserved_micro_usd'] for x in campaign['entries']);(target/'campaign-cost-audit.json').write_text(json.dumps({'calls':calls,'recorded_micro_usd':total,'tokens':tokens,'unresolved_reserved_micro_usd':0,'all_usage_recorded':True,'rate_recalculation':'PASS','campaign_reconciliation':'PASS','aws_invoice_reconciled':False,'ledgers':ledgers},indent=2)+'\n')
print(json.dumps({'methods':audited['methods'],'status_counts':audited['status_counts'],'batch_cost':audited['recorded_micro_usd'],'campaign_cost':total,'calls':calls},indent=2))
