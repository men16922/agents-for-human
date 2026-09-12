from pathlib import Path
from dataclasses import replace
import argparse, json, os, time
from rehearsal.agents.runner import read_settings, bedrock_model
from rehearsal.experiments.b3 import run_b3
from rehearsal.evaluation.frozen_run import run_cell, known_pair

root = Path.cwd()
base = root / '.local/nova-live-20260912'
parser = argparse.ArgumentParser()
parser.add_argument('stage', choices=['b3', 'frozen'])
parser.add_argument('id')
parser.add_argument('--method', choices=['B1', 'B2', 'B3'], default='B3')
parser.add_argument('--max-total-tokens', type=int, default=100000)
parser.add_argument('--max-input-tokens', type=int, default=8000)
args = parser.parse_args()
assert args.id.replace('-', '').isalnum()
for line in (base / 'nova.env').read_text().splitlines():
    key, value = line.split('=', 1)
    os.environ[key] = value
settings = replace(read_settings(root), max_model_calls=48, max_tool_calls=60,
                   max_total_tokens=args.max_total_tokens,input_limit=args.max_input_tokens)
path = base / 'campaign.json'
campaign = json.loads(path.read_text())
assert not any(e['reserved_micro_usd'] for e in campaign['entries']), 'Unresolved prior stage'
assert not any(e['id'] == args.id for e in campaign['entries']), 'Never overwrite an attempt'
used = sum(e['recorded_micro_usd'] for e in campaign['entries'])
assert used + settings.budget_micro_usd <= campaign['admission_limit_micro_usd']
entry = {'id': args.id, 'scope': 'live-model', 'stage': args.stage,
         'status': 'ADMITTED', 'recorded_micro_usd': 0,
         'reserved_micro_usd': settings.budget_micro_usd,
         'directory': str(base / args.id), 'settings': {'max_model_calls':48,'max_tool_calls':60,'max_total_tokens':settings.max_total_tokens,'input_limit':settings.input_limit}}
campaign['entries'].append(entry)
path.write_text(json.dumps(campaign, indent=2) + '\n')
os.umask(0o077)
start = time.perf_counter()
if args.stage == 'b3':
    report = run_b3(lambda _: bedrock_model(settings), lambda _: bedrock_model(settings),
                    settings, base / args.id,
                    json.loads((root/'scenarios/normal-v1.json').read_text()), 'live-model')
    usage = report['usage']
else:
    training, evaluation = known_pair(root)
    report = run_cell(args.method, lambda k,p: bedrock_model(settings), settings,
                      base / args.id, training, evaluation, 'live-model')
    usage = report['total_usage']
entry.update(status=report['status'], recorded_micro_usd=usage['recorded_micro_usd'],
             elapsed_seconds=time.perf_counter()-start)
if usage['all_usage_recorded']:
    entry['reserved_micro_usd'] = 0
else:
    entry['status'] = 'USAGE_UNRESOLVED'
path.write_text(json.dumps(campaign, indent=2) + '\n')
print(json.dumps({'entry':entry,'report':report},indent=2))
