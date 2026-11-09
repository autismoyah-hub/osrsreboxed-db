"""UNRUN read-only bucket-discovery caller draft. Not selected or authorized.

Uses a reviewed, privately prepared SDK snapshot and exact auth-child source.
Output contains private provider metadata; retain privately. No job/write method.
"""
import argparse,base64,hashlib,json,os,pathlib,resource,shutil,signal,subprocess,sys,time,types
HERE=pathlib.Path(__file__).resolve().parent
INTERPRETER='/usr/bin/python3.12'
INTERPRETER_SHA='c2c20b4745d447551221ec3d4e70f92c270c4609fe3df34fc52ea6dd46e92273'
FILES={'adapter':('hf-bucket-readonly-proposal.py','f23d68b0e8f12abc5bb3e7a3da7b7fa253a81e1c089bee19ca65fd3dda239469'),
       'entry':('bucket-list-proposal.py','996a5d714e0311a0ae9fa09262abe16d845640d7fd6a9e3bedebc8708984b230'),
       'authChild':('authenticated-child-snapshot-command.py','00ff45d75be1eae3bc8f04995cfb8bcbe2bc5adc28c1162b843cfe88c87024f9'),
       'snapshot':('bucket-sdk-snapshot.py','435a62f3e42ad4fa4380cb26316210d7d52d98f4d47e68c2574c8665b70ef912')}
LIMIT=1024*1024

def sha(b):return hashlib.sha256(b).hexdigest()
def bound(path,digest):
 data=path.read_bytes()
 if sha(data)!=digest:raise RuntimeError('source identity mismatch')
 return data
def load(path,digest):
 raw=bound(path,digest);module=types.ModuleType('reviewed_snapshot');module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);return module

def main():
 p=argparse.ArgumentParser();p.add_argument('--sdk-manifest',type=pathlib.Path,required=True);p.add_argument('--sdk-manifest-sha256',required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 if not __debug__ or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:raise RuntimeError('isolated interpreter required')
 if str(pathlib.Path(sys.executable).resolve())!=INTERPRETER or sha(pathlib.Path(sys.executable).read_bytes())!=INTERPRETER_SHA:raise RuntimeError('interpreter mismatch')
 manifest=a.sdk_manifest.resolve(strict=True);bound(manifest,a.sdk_manifest_sha256)
 for path,digest in FILES.values():bound(HERE/path,digest)
 home=HERE/'discovery-runs'
 if home.is_symlink() or not home.is_dir() or home.stat().st_mode & 0o077:raise RuntimeError('private discovery root required')
 if a.output.parent.resolve()!=home.resolve() or a.output.name in ('','.','..'):raise RuntimeError('output outside private discovery root')
 root=home/a.output.name
 if root.exists() or root.is_symlink():raise RuntimeError('output not fresh')
 root.mkdir(mode=0o700);fd=os.open(str(root.parent),os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 receipt={'status':'UNKNOWN','exit':None,'timedOut':False,'processGroupGone':False,'errors':[],'source':'read-only bucket discovery','sdkManifestSHA256':a.sdk_manifest_sha256,'scope':'SDK-returned namespace metadata only; no permissions, persistence or global census proof'}
 started=time.monotonic();sdkroot=None;proc=None
 try:
  sdk=load(HERE/FILES['snapshot'][0],FILES['snapshot'][1]);child=load(HERE/FILES['authChild'][0],FILES['authChild'][1]);sdkroot,site=sdk.build(manifest);sdk.verify(site,manifest)
  adapter=bound(HERE/FILES['adapter'][0],FILES['adapter'][1]);entry=HERE/FILES['entry'][0]
  cmd=[INTERPRETER,'-I','-S','-B','-c',child.CHILD_BOOTSTRAP,base64.b64encode(adapter).decode(),FILES['adapter'][1],str(HERE/FILES['adapter'][0]),str(site),'--entry',str(entry),'--entry-sha256',FILES['entry'][1]]
  if any('\0' in x or len(x.encode())+1>=131072 for x in cmd):raise RuntimeError('argv bound')
  def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(LIMIT,LIMIT))
  with (root/'stdout.private').open('xb') as out,(root/'stderr.private').open('xb') as err:
   proc=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True,preexec_fn=limit)
   try:receipt['exit']=proc.wait(timeout=120)
   except subprocess.TimeoutExpired:
    receipt['timedOut']=True
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    receipt['exit']=proc.wait(timeout=10)
   finally:
    try:os.killpg(proc.pid,0)
    except ProcessLookupError:receipt['processGroupGone']=True
    else:
     receipt['errors'].append('LEFTOVER_GROUP')
     try:os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError:pass
    out.flush();os.fsync(out.fileno());err.flush();os.fsync(err.fileno())
  sdk.verify(site,manifest);receipt['sdkPrePost']='MATCH'
  raw=(root/'stdout.private').read_bytes()
  if len(raw)>LIMIT or (root/'stderr.private').stat().st_size>LIMIT:raise RuntimeError('capture bound')
  data=json.loads(raw)
  if receipt['exit']!=0 or receipt['timedOut'] or not receipt['processGroupGone'] or receipt['errors'] or data.get('status')!='LIST_ITERATION_RETURNED' or data.get('namespace')!='Autismo-Yah' or type(data.get('count')) is not int or data['count']!=len(data.get('ids',[])) or data['count']>100:raise RuntimeError('incomplete discovery')
  receipt['status']='ITERATION_RETURNED_METADATA_ONLY';receipt['count']=data['count']
 except BaseException as exc:
  receipt['errors'].append(type(exc).__name__)
 finally:
  if sdkroot is not None:
   try:shutil.rmtree(sdkroot)
   except BaseException as exc:receipt['errors'].append('snapshot cleanup '+type(exc).__name__);receipt['status']='UNKNOWN'
  for name in ('stdout.private','stderr.private'):
   f=root/name
   if f.exists():
    try:
     data=f.read_bytes();receipt[name]={'bytes':len(data),'sha256':sha(data)}
    except BaseException as exc:receipt['errors'].append('capture read '+type(exc).__name__);receipt['status']='UNKNOWN'
  if receipt['errors']:receipt['status']='UNKNOWN'
  receipt['elapsedSeconds']=round(time.monotonic()-started,3)
  with (root/'receipt.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
  # Do not print private bucket IDs or child output.
  print(json.dumps({'status':receipt['status'],'count':receipt.get('count'),'errors':receipt['errors'],'scope':receipt['scope']}),flush=True)
 if receipt['status']!='ITERATION_RETURNED_METADATA_ONLY':raise RuntimeError('discovery incomplete; no retry')
if __name__=='__main__':main()
