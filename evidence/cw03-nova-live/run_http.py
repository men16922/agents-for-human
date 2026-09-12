from pathlib import Path
from dataclasses import replace
import json, os, sys, time
root = Path.cwd()
base = root / '.local/nova-live-20260912'
sys.path.insert(0, str(root / 'scripts/commerce'))
from model_session import Session
from rehearsal.agents.runner import read_settings, bedrock_model
from rehearsal.commerce.learning_budget import prepare, B3Carryover
from rehearsal.commerce.model_runner import execute_http
from rehearsal.operating.client import OperatingClient

os.umask(0o077)
for line in (base / 'nova.env').read_text().splitlines():
    key, value = line.split('=', 1)
    os.environ[key] = value
settings = replace(read_settings(root), max_model_calls=48, max_tool_calls=60)
learning = base / 'b3-price-03'
policy = base / 'http-policy.json'
frozen = prepare(learning, policy, settings, 'live-model')
carry = B3Carryover(learning, policy, settings, 'live-model')
prior = carry.ledger.report()['recorded_micro_usd']
path = base / 'campaign.json'
campaign = json.loads(path.read_text())
assert not any(e['reserved_micro_usd'] for e in campaign['entries'])
assert not any(e['id'] == 'http-01' for e in campaign['entries'])
assert sum(e['recorded_micro_usd'] for e in campaign['entries']) + settings.budget_micro_usd <= campaign['admission_limit_micro_usd']
entry = {'id':'http-01','stage':'B3-policy-HTTP','scope':'live-model',
         'status':'ADMITTED','recorded_micro_usd':0,'reserved_micro_usd':settings.budget_micro_usd,
         'learning_id':'b3-price-03','cost_basis':'increment beyond recorded learning cost'}
campaign['entries'].append(entry)
path.write_text(json.dumps(campaign,indent=2)+'\n')
model = bedrock_model(settings)
session = Session(policy, fixture=False)
client = None
start = time.perf_counter()
try:
    session_path = session.start()
    config = json.loads((session_path/'buyer-config.json').read_text())
    execution = root/'.local/commerce-model'/config['run_id']
    entry.update(session_directory=str(session_path),directory=str(execution))
    path.write_text(json.dumps(campaign,indent=2)+'\n')
    client = OperatingClient('http://127.0.0.1:18001',config['run_id'],config['buyer_token'],timeout=10)
    report = execute_http(model, settings, client, execution, config['expected_goal'],
                          config['expected_budget'],frozen,'live-model',carryover=carry)
    entry['runtime_status'] = report['runtime_status']
finally:
    session.close('NOVA_LIVE_HTTP_FINISHED')
    if client:
        client.close()
    usage = carry.ledger.report()
    entry['recorded_micro_usd'] = usage['recorded_micro_usd']-prior
    entry['elapsed_seconds'] = time.perf_counter()-start
    entry['status'] = session.record['state']
    if usage['all_usage_recorded']:
        entry['reserved_micro_usd'] = 0
    else:
        entry['status'] = 'USAGE_UNRESOLVED'
    path.write_text(json.dumps(campaign,indent=2)+'\n')
    (base/'http-result.json').write_text(json.dumps({'entry':entry,'session':session.record,
               'accounting':carry.accounting()},indent=2)+'\n')
    print(json.dumps(entry,indent=2))
