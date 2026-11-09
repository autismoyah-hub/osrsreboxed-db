"""UNRUN read-only discovery draft. No execution authority or SDK is supplied.

Private SDK-returned metadata only. Missing/failed receipts are UNKNOWN.
No claim of escaped-descendant closure, write permission or global census.
"""
import argparse,base64,email.parser,hashlib,json,os,pathlib,re,resource,shutil,signal,subprocess,sys,time,types
HERE=pathlib.Path(__file__).resolve().parent
INTERPRETER='/usr/bin/python3.12'
INTERPRETER_SHA='c2c20b4745d447551221ec3d4e70f92c270c4609fe3df34fc52ea6dd46e92273'
OWNER='4e81ba8a-625e-4909-8635-5bc9ca91cd77'
FILES={'adapter':('hf-bucket-readonly-proposal.py','f23d68b0e8f12abc5bb3e7a3da7b7fa253a81e1c089bee19ca65fd3dda239469'),
       'entry':('bucket-list-proposal.py','996a5d714e0311a0ae9fa09262abe16d845640d7fd6a9e3bedebc8708984b230'),
       'authChild':('authenticated-child-snapshot-command.py','00ff45d75be1eae3bc8f04995cfb8bcbe2bc5adc28c1162b843cfe88c87024f9'),
       'snapshot':('bucket-sdk-snapshot.py','8256d1e5cfa5d7f82ac6049c6889e64497c2b9566cfc44a0dae915b74e4afe77')}
LIMIT=1024*1024
MANIFEST_LIMIT=4*1024*1024

def sha(b):return hashlib.sha256(b).hexdigest()
def bound(path,digest,limit=MANIFEST_LIMIT):
 if not re.fullmatch('[a-f0-9]{64}',digest) or path.stat().st_size>limit:raise RuntimeError('input bound')
 data=path.read_bytes()
 if sha(data)!=digest:raise RuntimeError('source identity mismatch')
 return data
def load(path,digest):
 raw=bound(path,digest);module=types.ModuleType('reviewed_snapshot');module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);return module

def validate_manifest(raw):
 rows=json.loads(raw)
 if not isinstance(rows,list) or not 0<len(rows)<=10000:raise RuntimeError('manifest count')
 seen=set()
 for row in rows:
  if not isinstance(row,dict) or set(row)!={'path','bytes','sha256'}:raise RuntimeError('manifest schema')
  name=row['path'];parts=name.split('/') if isinstance(name,str) else []
  if not parts or any(x in ('','.','..') for x in parts) or name in seen or type(row['bytes']) is not int or row['bytes']<0 or not isinstance(row['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',row['sha256']):raise RuntimeError('manifest entry')
  seen.add(name)
 if sum(name.startswith('huggingface_hub-2.4.0.dist-info/') and name.endswith('/METADATA') for name in seen)!=1:raise RuntimeError('SDK version manifest')
 return rows

def group_gone(pid):
 try:os.killpg(pid,0)
 except ProcessLookupError:return True
 return False

def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=pathlib.Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--sdk-manifest',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 if not __debug__ or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:raise RuntimeError('isolated interpreter required')
 if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):raise RuntimeError('pidfd unavailable')
 if str(pathlib.Path(sys.executable).resolve())!=INTERPRETER or sha(pathlib.Path(sys.executable).read_bytes())!=INTERPRETER_SHA:raise RuntimeError('interpreter mismatch')
 plan=json.loads(bound(a.plan.resolve(strict=True),a.plan_sha256));expected={'owner','action','sdkVersion','sdkManifestSHA256','executionHold','maxResults','timeoutSeconds'}
 if set(plan)!=expected or plan['owner']!=OWNER or plan['action']!='READ_ONLY_BUCKET_LIST' or plan['sdkVersion']!='2.4.0' or plan['executionHold'] or plan['maxResults']!=100 or plan['timeoutSeconds']!=120:raise RuntimeError('unselected or mismatched plan')
 manifest=a.sdk_manifest.resolve(strict=True);manifest_raw=bound(manifest,plan['sdkManifestSHA256']);validate_manifest(manifest_raw)
 for path,digest in FILES.values():bound(HERE/path,digest)
 home=HERE/'discovery-runs'
 if home.is_symlink() or not home.is_dir() or home.stat().st_uid!=os.geteuid() or home.stat().st_mode&0o077:raise RuntimeError('private owned discovery root required')
 if a.output.parent.resolve()!=home.resolve() or a.output.name in ('','.','..'):raise RuntimeError('output outside private discovery root')
 root=home/a.output.name
 if root.exists() or root.is_symlink():raise RuntimeError('output not fresh')
 # mkdir/parent-fsync failure may leave no receipt: operator must classify UNKNOWN.
 root.mkdir(mode=0o700);fd=os.open(str(root.parent),os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 receipt={'status':'UNKNOWN','planSHA256':a.plan_sha256,'owner':OWNER,'exit':None,'timedOut':False,'processGroupGone':None,'pid':None,'snapshotDisposition':'NOT_CREATED','errors':[],'sdkManifestSHA256':plan['sdkManifestSHA256'],'scope':'SDK-returned namespace metadata only; no permissions, persistence, global census or escaped-descendant proof'}
 started=time.monotonic();sdkroot=None;proc=None;pidfd=None;sdk=None;site=None
 try:
  sdk=load(HERE/FILES['snapshot'][0],FILES['snapshot'][1]);child=load(HERE/FILES['authChild'][0],FILES['authChild'][1]);sdkroot,site=sdk.build(manifest);receipt['snapshotDisposition']='PRESERVED_PENDING_CLOSURE';receipt['snapshotPath']=str(sdkroot);sdk.verify(site,manifest)
  metadata=list(site.glob('huggingface_hub-2.4.0.dist-info/METADATA'))
  if len(metadata)!=1 or email.parser.Parser().parsestr(metadata[0].read_text()).get('Version')!='2.4.0':raise RuntimeError('SDK version mismatch')
  adapter=bound(HERE/FILES['adapter'][0],FILES['adapter'][1]);entry=HERE/FILES['entry'][0]
  cmd=[INTERPRETER,'-I','-S','-B','-c',child.CHILD_BOOTSTRAP,base64.b64encode(adapter).decode(),FILES['adapter'][1],str(HERE/FILES['adapter'][0]),str(site),'--entry',str(entry),'--entry-sha256',FILES['entry'][1]]
  if any('\0' in x or len(x.encode())+1>=131072 for x in cmd):raise RuntimeError('argv bound')
  def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(LIMIT,LIMIT))
  with (root/'stdout.private').open('xb') as out,(root/'stderr.private').open('xb') as err:
   proc=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True,preexec_fn=limit);receipt['pid']=proc.pid
   pidfd=os.pidfd_open(proc.pid,0)
   try:receipt['exit']=proc.wait(timeout=120)
   except subprocess.TimeoutExpired:
    receipt['timedOut']=True
    try:signal.pidfd_send_signal(pidfd,signal.SIGKILL);receipt['leaderPidfdKill']=True
    except ProcessLookupError:receipt['leaderPidfdKill']=False
    receipt['exit']=proc.wait(timeout=10)
   finally:
    out.flush();os.fsync(out.fileno());err.flush();os.fsync(err.fileno())
  sdk.verify(site,manifest);bound(manifest,plan['sdkManifestSHA256']);receipt['sdkPrePost']='MATCH'
  raw=(root/'stdout.private').read_bytes()
  if len(raw)>LIMIT or (root/'stderr.private').stat().st_size>LIMIT:raise RuntimeError('capture bound')
  data=json.loads(raw)
  ids=data.get('ids')
  if receipt['exit']!=0 or receipt['timedOut'] or data.get('status')!='LIST_ITERATION_RETURNED' or data.get('namespace')!='Autismo-Yah' or not isinstance(ids,list) or type(data.get('count')) is not int or data['count']!=len(ids) or len(ids)>100:raise RuntimeError('incomplete discovery')
  if any(not isinstance(x,str) or not re.fullmatch(r'Autismo-Yah/[A-Za-z0-9][A-Za-z0-9._-]{0,95}',x) for x in ids) or len(set(ids))!=len(ids):raise RuntimeError('invalid bucket identities')
  receipt['status']='ITERATION_RETURNED_METADATA_ONLY';receipt['count']=data['count']
 except BaseException as exc:
  if hasattr(exc,'snapshotPath'):
   receipt['snapshotPath']=exc.snapshotPath;receipt['snapshotDisposition']='PRESERVED_BUILD_FAILURE'
  receipt['errors'].append(type(exc).__name__);receipt['status']='UNKNOWN'
 finally:
  if proc is not None:
   try:
    if not group_gone(proc.pid):
     receipt['errors'].append('LEFTOVER_GROUP_NOT_SIGNALLED');receipt['status']='UNKNOWN'
    deadline=time.monotonic()+5
    while time.monotonic()<deadline and not group_gone(proc.pid):time.sleep(0.05)
    receipt['processGroupGone']=group_gone(proc.pid)
   except BaseException as exc:receipt['errors'].append('group closure '+type(exc).__name__);receipt['status']='UNKNOWN'
  else:receipt['processGroupGone']=True
  if pidfd is not None:
   try:os.close(pidfd)
   except BaseException as exc:receipt['errors'].append('pidfd close '+type(exc).__name__);receipt['status']='UNKNOWN'
  if sdkroot is not None and receipt['processGroupGone'] is True:
   try:shutil.rmtree(sdkroot);receipt['snapshotDisposition']='REMOVED_AFTER_GROUP_CLOSURE'
   except BaseException as exc:receipt['errors'].append('snapshot cleanup '+type(exc).__name__);receipt['status']='UNKNOWN'
  for name in ('stdout.private','stderr.private'):
   f=root/name
   if f.exists():
    try:
     if f.stat().st_size>LIMIT:raise RuntimeError('capture too large')
     data=f.read_bytes();receipt[name]={'bytes':len(data),'sha256':sha(data)}
    except BaseException as exc:receipt['errors'].append('capture read '+type(exc).__name__);receipt['status']='UNKNOWN'
  if receipt['errors'] or receipt['processGroupGone'] is not True:receipt['status']='UNKNOWN'
  receipt['elapsedSeconds']=round(time.monotonic()-started,3)
  # Exclusive receipt or fsync failure leaves missing/untrusted receipt: UNKNOWN.
  with (root/'receipt.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
  print(json.dumps({'status':receipt['status'],'count':receipt.get('count'),'errors':receipt['errors'],'snapshotDisposition':receipt['snapshotDisposition'],'scope':receipt['scope']}),flush=True)
 if receipt['status']!='ITERATION_RETURNED_METADATA_ONLY':raise RuntimeError('discovery incomplete; no retry')
if __name__=='__main__':main()
