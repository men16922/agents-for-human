from pathlib import Path
import json,hashlib,socket,subprocess,shutil,sys
from rehearsal.commerce.model_runner import attest
root=Path.cwd();e=root/'evidence/cw08-youtube-submission';capture=e/'capture';out=root/'submissions/video'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
a=attest(capture/'execution',capture/'session/selection.json');assert a['success'];assert a['evidence_review']['verdict']['spent']==380
r=json.loads((e/'report.json').read_text());assert sha(out/'rehearsal-demo.mp4')==r['video_sha256'];assert sha(capture/'browser/nova-live.webm')==r['capture_sha256']
for rel,expected in r['source_hashes'].items():assert sha(root/rel)==expected,rel
for p in (root/'src/rehearsal').rglob('*.py'):assert p.read_bytes()==(root/'evidence/cw07-nova-delivery-prompt/executed-source'/p.relative_to(root)).read_bytes(),p
campaign=json.loads((root/'.local/nova-live-20260912/campaign.json').read_text());cost=sum(x['recorded_micro_usd'] for x in campaign['entries']);reserved=sum(x['reserved_micro_usd'] for x in campaign['entries']);assert cost==4219026 and reserved==0
expected=json.loads((root/'evidence/cw06-nova-reactive/cleanup-audit.json').read_text())['containers'];containers=subprocess.check_output(['docker','ps','--format','{{.ID}} {{.Names}}'],text=True).splitlines();assert sorted(containers)==sorted(expected)
volumes=subprocess.check_output(['docker','volume','ls','-q'],text=True).splitlines();assert sorted(volumes)==sorted((root/'.local/nova-live-20260912/volumes-before.txt').read_text().splitlines())
ports=[18000,15173,18001,18002,19000,55432,56379]
for port in ports:
 with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',port))!=0,port
secrets=[]
for line in (root/'.env').read_text().splitlines():
 k,sep,v=line.partition('=');v=v.strip().strip('"').strip("'")
 if sep and len(v)>15 and any(x in k.lower() for x in ['key','secret','token','password']):secrets.append(v.encode())
config=json.loads((root/'.local/commerce/cw00-f94d15615950/model-session/buyer-config.json').read_text())
def secret_fields(obj):
 if isinstance(obj,dict):
  for k,v in obj.items():
   if isinstance(v,str) and len(v)>15 and any(x in k.lower() for x in ['token','secret','authorization','password']):secrets.append(v.encode())
   secret_fields(v)
 elif isinstance(obj,list):
  for v in obj:secret_fields(v)
secret_fields(config)
for directory in [e,out]:
 for file in directory.rglob('*'):
  if file.is_file():
   data=file.read_bytes();assert not any(secret in data for secret in secrets),file
build=root/'.local/youtube-submission-20260912';cleanup=json.loads((e/'cleanup.json').read_text())
for p in sorted(build.iterdir()):
 if p.is_file() and (p.name.startswith('segment-') or p.name.startswith('card-') and p.suffix=='.png' or p.name=='hold-label.png' or p.name=='rehearsal-draft.mp4'):
  if p.name=='rehearsal-draft.mp4':assert sha(p)==sha(out/'rehearsal-demo.mp4')
  cleanup['removed']=[x for x in cleanup['removed'] if x['path']!=str(p.relative_to(root))]
  cleanup['removed'].append({'path':str(p.relative_to(root)),'files':1,'bytes':p.stat().st_size,'reason':'Regenerable video rendering intermediate or hash-identical final copy'})
  p.unlink()
cleanup['removed_files']=sum(x['files'] for x in cleanup['removed']);cleanup['removed_bytes']=sum(x['bytes'] for x in cleanup['removed']);dump(e/'cleanup.json',cleanup)
shutil.copy2(build/'thumbnail.mjs',e/'thumbnail.mjs')
dump(e/'verification.json',{'scope':'local-youtube-deliverable-and-independent-copied-transaction-audit','attestation':a,'video_sha256':r['video_sha256'],'source_hashes_match':True,'product_python_sources_unchanged':58,'campaign_recorded_micro_usd':cost,'unresolved_reserved_micro_usd':reserved,'original_containers_preserved':containers,'volumes_unchanged':True,'volume_count':len(volumes),'free_ports':ports,'known_local_secret_matches':0,'known_secret_values_checked':len(secrets),'removed_files':cleanup['removed_files'],'removed_bytes':cleanup['removed_bytes'],'uploaded':False,'submitted':False})
print(json.dumps({'independent_verdict':a['evidence_review']['verdict'],'removed_bytes':cleanup['removed_bytes'],'removed_files':cleanup['removed_files'],'campaign_usd':cost/1e6,'volumes':len(volumes)},indent=2))
