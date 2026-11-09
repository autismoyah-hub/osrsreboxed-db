"""UNRUN synthetic-only supervisor draft. No network, provider, GAME or export."""
import ctypes, importlib.util, json, os, pathlib, signal, sys, tempfile, time

spec=importlib.util.spec_from_file_location('slug_runner',pathlib.Path(__file__).with_name('runner.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8'}

def children():
 text=pathlib.Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()
 return {int(x) for x in text.split()} if text else set()

def reap_all_owned():
 deadline=time.monotonic()+15;events=[];errors=[]
 try:
  while time.monotonic()<deadline:
   owned=children()
   if not owned:return {'status':'NO_DIRECT_CHILDREN','childrenRemaining':[],'events':events,'errors':errors}
   for pid in sorted(owned):
    fd=None
    try:
     waited,status=os.waitpid(pid,os.WNOHANG)
     if waited:
      events.append({'pid':pid,'action':'reaped','waitStatus':status});continue
     fd=os.pidfd_open(pid,0)
     if pid not in children():raise RuntimeError('child ownership changed')
     signal.pidfd_send_signal(fd,signal.SIGKILL)
     events.append({'pid':pid,'action':'pidfd-sigkill'})
    except (ProcessLookupError,ChildProcessError):events.append({'pid':pid,'action':'already-gone'})
    except BaseException as exc:errors.append(type(exc).__name__+': '+str(exc))
    finally:
     if fd is not None:
      try:os.close(fd)
      except BaseException as exc:errors.append('pidfd close: '+type(exc).__name__+': '+str(exc))
   time.sleep(0.02)
  return {'status':'UNKNOWN','childrenRemaining':sorted(children()),'events':events,'errors':errors}
 except BaseException as exc:
  errors.append('supervisor: '+type(exc).__name__+': '+str(exc))
  return {'status':'UNKNOWN','childrenRemaining':None,'events':events,'errors':errors}

def perform(label,code,expected,timeout=3):
 r.COMMAND_TIMEOUT_SECONDS=timeout;r.COMMANDS[label]=[sys.executable,'-c',code]
 try:r.run(label,[sys.executable,'-c',code],r.ROOT,env)
 except RuntimeError:
  if expected=='COMPLETE':raise
 else:
  if expected!='COMPLETE':raise AssertionError(label+' unexpectedly completed')
 result=json.loads((r.ROOT/(label+'.result.json')).read_text())
 assert result['status']==expected,(label,result)
 return result

def main():
 if sys.platform!='linux' or not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):raise RuntimeError('pidfd unavailable')
 libc=ctypes.CDLL(None,use_errno=True)
 if libc.prctl(36,1,0,0,0)!=0:raise RuntimeError('subreaper unavailable')
 state=ctypes.c_int()
 if libc.prctl(37,ctypes.byref(state),0,0,0)!=0 or state.value!=1 or children():raise RuntimeError('supervisor preconditions unavailable')
 fd=os.pidfd_open(os.getpid(),0)
 try:signal.pidfd_send_signal(fd,0)
 finally:os.close(fd)
 cleanup={'status':'UNKNOWN','childrenRemaining':None,'errors':['cleanup not attempted']};orphan_result=None
 try:
  with tempfile.TemporaryDirectory(prefix='slug-runner-controls-') as tmp:
   r.ROOT=pathlib.Path(tmp)
   x=perform('success',"print('synthetic success',flush=True)",'COMPLETE')
   assert x['exit']==0 and x['processGroupGone'] and not x['forcedCleanup']
   x=perform('timeout',"import time;print('synthetic partial',flush=True);time.sleep(30)",'UNKNOWN',0.5)
   assert x['timedOut'] and b'synthetic partial' in (r.ROOT/'timeout.stdout').read_bytes()
   x=perform('signal',"import os,signal;os.kill(os.getpid(),signal.SIGTERM)",'UNKNOWN')
   assert x['signal']==signal.SIGTERM
   orphan_result=perform('orphan',"import json,os,subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); print(json.dumps({'pid':p.pid,'pgid':os.getpgrp()}),flush=True)",'UNKNOWN')
   assert orphan_result['unexpectedLeftoverGroup'] and orphan_result['forcedCleanup']
   (r.ROOT/'collision.stdout').write_text('preexisting-sentinel')
   x=perform('collision',"raise SystemExit('should never run')",'UNKNOWN')
   assert x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
   assert (r.ROOT/'collision.stdout').read_text()=='preexisting-sentinel'
   (r.ROOT/'output-error.stdout').mkdir()
   x=perform('output-error',"raise SystemExit('should never run')",'UNKNOWN')
   assert x['errors'] and x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
 finally:
  cleanup=reap_all_owned()
  print(json.dumps({'event':'synthetic-supervisor-custody','cleanup':cleanup,'runnerGroupGone':orphan_result.get('processGroupGone') if orphan_result else None,'scope':'direct/adopted children only; no escaped-descendant or PID1 inference'}),flush=True)
  if cleanup['status']!='NO_DIRECT_CHILDREN' or cleanup['errors']:raise RuntimeError('supervisor cleanup incomplete')
 print('PASS: synthetic success, timeout partial, signal, orphan group, collision and output-open failure')
if __name__=='__main__':main()
