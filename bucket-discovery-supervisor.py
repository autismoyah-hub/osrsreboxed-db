"""UNRUN whole-caller supervisor draft. Read-only discovery remains held.

No provider authority is supplied. Any incomplete process or absent receipt is
UNKNOWN and must not trigger automatic rerun or snapshot deletion.
"""
import argparse,base64,hashlib,json,os,pathlib,re,resource,signal,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent
CALLER_SHA='8ac96a88da8d4fbd57bfe7c2149e2f7de73acf873f700d3a9d21f6712028017b'
INTERPRETER='/usr/bin/python3.12'
INTERPRETER_SHA='c2c20b4745d447551221ec3d4e70f92c270c4609fe3df34fc52ea6dd46e92273'
SNAPROOT=pathlib.Path('/tmp/slug-bucket-snapshots')
CHILD_BOOTSTRAP="""import base64,hashlib,sys,types
raw=base64.b64decode(sys.argv.pop(1),validate=True)
expected=sys.argv.pop(1);filename=sys.argv.pop(1)
if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit(1)
sys.argv[0]=filename
module=types.ModuleType('__main__')
module.__dict__.update(__file__=filename,__name__='__main__',__package__='',__spec__=None,__cached__=None)
sys.modules['__main__']=module
exec(compile(raw,filename,'exec'),module.__dict__)
"""
LIMIT=1024*1024
CHILD_FILE_LIMIT=32*1024*1024

def sha(data):return hashlib.sha256(data).hexdigest()
def checked(path,digest,limit):
 if not re.fullmatch('[0-9a-f]{64}',digest) or path.stat().st_size>limit:raise RuntimeError('input bound')
 raw=path.read_bytes()
 if sha(raw)!=digest:raise RuntimeError('input identity')
 return raw
def private_dir(path):
 if path.is_symlink() or not path.is_dir() or path.stat().st_uid!=os.geteuid() or path.stat().st_mode&0o077:raise RuntimeError('private owned directory required')
def group_gone(pid):
 try:os.killpg(pid,0)
 except ProcessLookupError:return True
 return False

def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=pathlib.Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--sdk-manifest',type=pathlib.Path,required=True);p.add_argument('--sdk-manifest-sha256',required=True);p.add_argument('--caller-output',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 if not __debug__ or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:raise RuntimeError('isolated interpreter required')
 if str(pathlib.Path(sys.executable).resolve())!=INTERPRETER or sha(pathlib.Path(sys.executable).read_bytes())!=INTERPRETER_SHA:raise RuntimeError('interpreter identity')
 if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):raise RuntimeError('pidfd unavailable')
 caller=HERE/'bucket-discovery-caller.py';caller_snapshot=checked(caller,CALLER_SHA,1024*1024);plan=json.loads(checked(a.plan,a.plan_sha256,1024*1024));checked(a.sdk_manifest,a.sdk_manifest_sha256,4*1024*1024)
 if plan.get('sdkManifestSHA256')!=a.sdk_manifest_sha256:raise RuntimeError('plan manifest mismatch')
 private_dir(SNAPROOT);home=HERE/'supervisor-runs';private_dir(home)
 if a.output.parent.resolve()!=home.resolve() or a.output.name in ('','.','..'):raise RuntimeError('output outside private root')
 root=home/a.output.name
 if root.exists() or root.is_symlink():raise RuntimeError('output not fresh')
 root.mkdir(mode=0o700);fd=os.open(str(home),os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 before=sorted(x.name for x in SNAPROOT.iterdir());result={'status':'UNKNOWN','planSHA256':a.plan_sha256,'sdkManifestSHA256':a.sdk_manifest_sha256,'callerSHA256':CALLER_SHA,'pid':None,'exit':None,'timedOut':False,'processGroupGone':None,'snapshotsBefore':before,'nestedAuthAction':'POSSIBLY_ACTIVE_UNTIL_INDEPENDENT_RECONCILIATION','snapshotInventoryScope':'point-in-time names only; nested child may create later','errors':[],'scope':'outer caller process group only; nested auth child uses another session, escaped descendants and transient mutation unproven'}
 proc=None;pidfd=None;started=time.monotonic()
 try:
  cmd=[INTERPRETER,'-I','-S','-B','-c',CHILD_BOOTSTRAP,base64.b64encode(caller_snapshot).decode('ascii'),CALLER_SHA,str(caller),'--plan',str(a.plan.resolve()),'--plan-sha256',a.plan_sha256,'--sdk-manifest',str(a.sdk_manifest.resolve()),'--output',str(a.caller_output)]
  def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(CHILD_FILE_LIMIT,CHILD_FILE_LIMIT))
  with (root/'stdout.private').open('xb') as out,(root/'stderr.private').open('xb') as err:
   proc=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True,preexec_fn=limit);result['pid']=proc.pid;pidfd=os.pidfd_open(proc.pid,0)
   try:result['exit']=proc.wait(timeout=180)
   except subprocess.TimeoutExpired:
    result['timedOut']=True
    try:signal.pidfd_send_signal(pidfd,signal.SIGKILL);result['leaderPidfdKill']=True
    except ProcessLookupError:result['leaderPidfdKill']=False
    result['exit']=proc.wait(timeout=10)
   finally:out.flush();os.fsync(out.fileno());err.flush();os.fsync(err.fileno())
  checked(caller,CALLER_SHA,1024*1024);checked(a.plan,a.plan_sha256,1024*1024);checked(a.sdk_manifest,a.sdk_manifest_sha256,4*1024*1024)
  result['sourcePrePost']='MATCH'
  if result['exit']==0 and not result['timedOut']:result['status']='CALLER_EXITED_ZERO_AWAIT_RECEIPT_REVIEW'
 except BaseException as exc:result['errors'].append(type(exc).__name__);result['status']='UNKNOWN'
 finally:
  if proc is not None:
   try:result['processGroupGone']=group_gone(proc.pid)
   except BaseException as exc:result['errors'].append('group check '+type(exc).__name__)
  else:result['processGroupGone']=True
  if pidfd is not None:
   try:os.close(pidfd)
   except BaseException as exc:result['errors'].append('pidfd close '+type(exc).__name__)
  try:result['snapshotsAfter']=sorted(x.name for x in SNAPROOT.iterdir())
  except BaseException as exc:result['errors'].append('snapshot inventory '+type(exc).__name__)
  for name in ('stdout.private','stderr.private'):
   f=root/name
   if f.exists():
    try:
     if f.stat().st_size>LIMIT:raise RuntimeError('capture size')
     b=f.read_bytes();result[name]={'bytes':len(b),'sha256':sha(b)}
    except BaseException as exc:result['errors'].append('capture read '+type(exc).__name__)
  if result['errors'] or result['timedOut'] or result['processGroupGone'] is not True:result['status']='UNKNOWN'
  result['elapsedSeconds']=round(time.monotonic()-started,3)
  # Missing or failed receipt/fsync is UNKNOWN; never delete snapshots here.
  with (root/'receipt.json').open('x',encoding='utf-8') as f:json.dump(result,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
  print(json.dumps({'status':result['status'],'errors':result['errors'],'scope':result['scope']}),flush=True)
 if result['status']!='CALLER_EXITED_ZERO_AWAIT_RECEIPT_REVIEW':raise RuntimeError('supervisor incomplete; no retry')
if __name__=='__main__':main()
