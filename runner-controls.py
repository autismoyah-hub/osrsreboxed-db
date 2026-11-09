"""UNRUN synthetic-only draft. No network, provider, GAME, source fetch or export."""
import ctypes, importlib.util, json, os, pathlib, signal, sys, tempfile, threading, time

spec=importlib.util.spec_from_file_location('slug_runner',pathlib.Path(__file__).with_name('runner.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8'}
libc=ctypes.CDLL(None,use_errno=True)
if sys.platform!='linux' or libc.prctl(36,1,0,0,0)!=0:raise RuntimeError('subreaper unavailable')
state=ctypes.c_int()
if libc.prctl(37,ctypes.byref(state),0,0,0)!=0 or state.value!=1:raise RuntimeError('subreaper not active')

def perform(label,code,expected,timeout=3):
 r.COMMAND_TIMEOUT_SECONDS=timeout
 r.COMMANDS[label]=[sys.executable,'-c',code]
 try:r.run(label,[sys.executable,'-c',code],r.ROOT,env)
 except RuntimeError:
  if expected=='COMPLETE':raise
 else:
  if expected!='COMPLETE':raise AssertionError(label+' unexpectedly completed')
 result=json.loads((r.ROOT/(label+'.result.json')).read_text())
 assert result['status']==expected,(label,result)
 return result

with tempfile.TemporaryDirectory(prefix='slug-runner-controls-') as tmp:
 r.ROOT=pathlib.Path(tmp)
 x=perform('success',"print('synthetic success',flush=True)",'COMPLETE')
 assert x['exit']==0 and x['processGroupGone'] and not x['forcedCleanup']
 x=perform('timeout',"import time;print('synthetic partial',flush=True);time.sleep(30)",'UNKNOWN',0.5)
 assert x['timedOut'] and b'synthetic partial' in (r.ROOT/'timeout.stdout').read_bytes()
 x=perform('signal',"import os,signal;os.kill(os.getpid(),signal.SIGTERM)",'UNKNOWN')
 assert x['signal']==signal.SIGTERM
 orphan_state={'pid':None,'pgid':None,'reaped':False,'waitStatus':None,'error':None}
 def reap_owned_orphan():
  deadline=time.monotonic()+20;path=r.ROOT/'orphan.stdout'
  while time.monotonic()<deadline:
   if orphan_state['pid'] is None and path.exists():
    try:
     row=json.loads(path.read_text().splitlines()[0]);pid=row['pid'];pgid=row['pgid']
     if type(pid)!=int or pid<=1 or type(pgid)!=int or pgid<=1 or pgid==os.getpgrp():raise RuntimeError('invalid child identity')
     orphan_state['pid']=pid;orphan_state['pgid']=pgid
    except (IndexError,ValueError,KeyError):pass
   if orphan_state['pid'] is not None:
    try:
     pid,status=os.waitpid(orphan_state['pid'],os.WNOHANG)
     if pid:
      orphan_state['reaped']=True;orphan_state['waitStatus']=status;return
    except ChildProcessError:pass
   time.sleep(0.02)
  orphan_state['error']='orphan was not reaped within deadline'
 thread=threading.Thread(target=reap_owned_orphan,daemon=True);thread.start();orphan_result=None
 try:
  orphan_result=perform('orphan',"import json,os,subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); print(json.dumps({'pid':p.pid,'pgid':os.getpgrp()}),flush=True)",'UNKNOWN')
  assert orphan_result['unexpectedLeftoverGroup'] and orphan_result['forcedCleanup']
 finally:
  thread.join(timeout=21)
  if not orphan_state['reaped'] and orphan_state['pid']:
   try:os.kill(orphan_state['pid'],signal.SIGKILL)
   except ProcessLookupError:pass
   try:os.waitpid(orphan_state['pid'],0);orphan_state['reaped']=True
   except ChildProcessError:pass
  group_gone=False
  if orphan_state['pgid']:
   try:os.killpg(orphan_state['pgid'],0)
   except ProcessLookupError:group_gone=True
  print(json.dumps({'event':'synthetic-orphan-custody',**orphan_state,'runnerGroupGone':orphan_result.get('processGroupGone') if orphan_result else None,'groupGoneAfterReap':group_gone}),flush=True)
 if thread.is_alive() or not orphan_state['reaped'] or orphan_state['error'] or not group_gone:raise RuntimeError('synthetic orphan cleanup incomplete')
 (r.ROOT/'collision.stdout').write_text('preexisting-sentinel')
 x=perform('collision',"raise SystemExit('should never run')",'UNKNOWN')
 assert x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
 assert (r.ROOT/'collision.stdout').read_text()=='preexisting-sentinel'
 # A directory at the output path exercises an exclusive-open failure.
 (r.ROOT/'output-error.stdout').mkdir()
 x=perform('output-error',"raise SystemExit('should never run')",'UNKNOWN')
 assert x['errors'] and x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
print('PASS: synthetic success, timeout partial, signal, orphan group, collision and output-open failure')
