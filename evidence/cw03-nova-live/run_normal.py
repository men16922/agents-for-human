from pathlib import Path
import json, os, time
from rehearsal.agents.runner import read_settings, bedrock_model, execute

root = Path.cwd()
base = root / '.local/nova-live-20260912'
for line in (base / 'nova.env').read_text().splitlines():
    key, value = line.split('=', 1)
    os.environ[key] = value
settings = read_settings(root)
campaign_path = base / 'campaign.json'
campaign = json.loads(campaign_path.read_text())
assert not campaign['entries'], 'Do not rerun or overwrite an existing experiment'
entry = {'id': 'nova-normal-01', 'scope': 'live-model', 'status': 'ADMITTED',
         'reserved_micro_usd': settings.budget_micro_usd,
         'recorded_micro_usd': 0, 'directory': str(base / 'normal-01')}
assert entry['reserved_micro_usd'] <= campaign['admission_limit_micro_usd']
campaign['entries'].append(entry)
campaign_path.write_text(json.dumps(campaign, indent=2) + '\n')
os.umask(0o077)
start = time.perf_counter()
report = execute(bedrock_model(settings), settings, base / 'normal-01',
                 json.loads((root / 'scenarios/normal-v1.json').read_text()),
                 entry['id'], 'live-model')
entry['status'] = report['runtime_status']
entry['recorded_micro_usd'] = report['usage']['recorded_micro_usd']
entry['elapsed_seconds'] = time.perf_counter() - start
entry['success'] = report['success']
if report['usage']['all_usage_recorded']:
    entry['reserved_micro_usd'] = 0
else:
    entry['status'] = 'USAGE_UNRESOLVED'
campaign_path.write_text(json.dumps(campaign, indent=2) + '\n')
print(json.dumps({'entry': entry, 'verdict': report['verdict'], 'usage': report['usage']}, indent=2))
