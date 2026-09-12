from pathlib import Path
import collections,gzip,hashlib,json,re,tarfile,subprocess
root=Path.cwd();base=root/'.local/release-candidate-20260912';source=base/'source'
manifest=json.loads((base/'source-manifest.json').read_text());known=set()
def collect(x):
 if isinstance(x,dict):
  for key,value in x.items():
   if isinstance(value,str) and (key.lower() in {'token','password','secret','jwt','buyer','observer','control','seller','observer_token','buyer_token'} or key.lower().endswith('_token')):
    if len(value)>=16:known.add(value.removeprefix('Bearer ').encode())
   else:collect(value)
 elif isinstance(x,list):
  for value in x:collect(value)
inputs=[]
for name in ('credentials.json','buyer-config.json','observer-buyer.json'):
 for p in (root/'.local').rglob(name):
  if p.is_file():
   try:collect(json.loads(p.read_text()));inputs.append(p)
   except (ValueError,UnicodeError):pass
for line in (root/'.env').read_text().splitlines():
 key,_,value=line.partition('=')
 if key in {'POSTGRES_PASSWORD','REDIS_PASSWORD','JWT_SECRET','COOKIE_SECRET'} and value:known.add(value.encode())
tokens=re.compile(rb'[A-Za-z0-9_-]{16,}(?:\.[A-Za-z0-9_-]+)*')
for name,record in manifest['files'].items():
 p=source/name;raw=p.read_bytes()
 assert hashlib.sha256(raw).hexdigest()==record['sha256'],name
 assert not known.intersection(tokens.findall(raw)),name
archive=base/'rehearsal-source.tar.gz'
with archive.open('xb') as output,gzip.GzipFile(filename='',mode='wb',fileobj=output,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as tar:
 for name,record in manifest['files'].items():
  info=tar.gettarinfo(str(source/name),arcname='rehearsal/'+name)
  assert info.isfile()
  info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
  info.mode=0o755 if record['executable'] else 0o644
  with (source/name).open('rb') as data:tar.addfile(info,data)
extracted=base/'extracted';extracted.mkdir(exist_ok=False)
with tarfile.open(archive,'r:gz') as tar:
 for member in tar.getmembers():
  assert member.isfile() and member.name.startswith('rehearsal/') and '..' not in Path(member.name).parts
 tar.extractall(extracted,filter='data')
copy=extracted/'rehearsal'
actual={str(p.relative_to(copy)) for p in copy.rglob('*') if p.is_file()}
assert actual==set(manifest['files'])
for name,record in manifest['files'].items():
 p=copy/name
 assert hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256']
 assert bool(p.stat().st_mode&0o100)==record['executable']
completed=subprocess.run(['python3','scripts/check.py'],cwd=copy,text=True,capture_output=True)
(base/'extracted-doc-check.log').write_text(completed.stdout+completed.stderr)
assert completed.returncode==0
exts=collections.Counter(Path(n).suffix for n in actual)
result={'scope':'local-unpublished-source-package','files':len(actual),'source_bytes':manifest['total_bytes'],'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'archive_path':str(archive.relative_to(root)),'extracted_hashes_and_modes_match':True,'extracted_document_gate':'PASS','runtime_gate_in_extracted_tree':'NOT_RUN; dependencies intentionally absent','known_local_credential_files_scanned':len(inputs),'known_local_secret_values_scanned':len(known),'known_local_secret_matches':0,'fixture_sqlite_files':exts['.sqlite3'],'dependency_directories_included':False,'symlinks_or_special_files_included':False,'publication':False,'actual_model_calls':0,'limitations':['Pattern and known-value scans are not universal secret detection.','This candidate predates its audit/checkpoint documents and future real-model results.','No public repository, release, independent installation, or final submission is established.']}
(base/'package-report.json').write_text(json.dumps(result,indent=2)+'\n')
print(result)
