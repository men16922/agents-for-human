from pathlib import Path
import hashlib,json,socket,subprocess,shutil
root=Path.cwd();base=root/'.local/nova-live-20260912';dest=root/'evidence/cw09-nova-final'
def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def manifest(d):
 records={}
 for p in sorted(d.rglob('*')):
  if p.is_file() and p!=d/'artifact-manifest.json':
   b=p.read_bytes();records[str(p.relative_to(d))]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 dump(d/'artifact-manifest.json',{'scope':'retained-local-evidence','files':records,'file_count':len(records)})
 return len(records)
new={}
for name in ['cw07-nova-prospective','cw07-nova-delivery-prompt','cw08-nova-final-video','cw05-nova-supplier-audit']:
 new[name]=manifest(root/'evidence'/name)
checked=0
for name in ['cw03-nova-live','cw06-nova-reactive','cw08-nova-video',*new]:
 d=root/'evidence'/name;m=json.loads((d/'artifact-manifest.json').read_text())
 for n,r in m['files'].items():
  p=d/n;assert p.is_file(),(name,n)
  assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],(name,n)
  assert p.stat().st_size==r['bytes'],(name,n)
  checked+=1
ports=[18000,15173,18001,19000,55432,56379]
for port in ports:
 with socket.socket() as s:assert s.connect_ex(('127.0.0.1',port))!=0,port
containers=subprocess.check_output(['docker','ps','--format','{{.ID}} {{.Names}}'],text=True).splitlines()
expected=json.loads((root/'evidence/cw06-nova-reactive/cleanup-audit.json').read_text())['containers']
assert sorted(containers)==sorted(expected)
volumes=subprocess.check_output(['docker','volume','ls','-q'],text=True).splitlines()
assert sorted(volumes)==sorted((base/'volumes-before.txt').read_text().splitlines())
status=json.loads((base/'campaign.json').read_text())
assert sum(e.get('reserved_micro_usd',0) for e in status['entries'])==0
assert sum(e.get('recorded_micro_usd',0) for e in status['entries'])==4191815
assert not any(e['status']=='RUNNING' for e in status['entries'])
post=root/'evidence/cw07-nova-delivery-prompt/executed-source'
files=list((root/'src/rehearsal').rglob('*.py'))
assert len(files)==58
for p in files:assert p.read_bytes()==(post/p.relative_to(root)).read_bytes(),p
for name in ['build_nova_submission_video.py','check_video.mjs','video_cards.mjs']:
 assert (root/'scripts/dev'/name).read_bytes()==(root/'evidence/cw08-nova-final-video'/name).read_bytes(),name
report={'scope':'local-final-evidence-and-cleanup-not-publication','artifact_files_hash_verified':checked,'new_artifact_counts':new,'current_product_source_files_matching_post_change_pilot':58,'current_video_builder_sources_match':True,'recorded_micro_usd':4191815,'unresolved_reserved_micro_usd':0,'paid_jobs_running':False,'free_ports':ports,'original_containers_preserved':containers,'volume_count':len(volumes),'volumes_unchanged':True,'publication':False,'independent_host_reproduction':False,'human_observation_participants':0,'source_package_report_location':'.local/release-candidate-nova-20260912-r2/package-report.json'}
dump(dest/'verification.json',report)
shutil.copy2(base/'final_submission_audit.py',dest/'final_submission_audit.py')
manifest(dest)
print(json.dumps(report,indent=2))
