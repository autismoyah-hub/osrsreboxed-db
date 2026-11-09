"""UNRUN synthetic-only draft. No network, provider, GAME, source fetch or export."""
import ctypes, importlib.util, json, os, pathlib, signal, sys, tempfile, time

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
 # This control process is the dedicated subreaper and starts no unrelated children.
 # Cleanup uses Linux child ownership and pidfds; no thread may race reaping.
 def children():
  text=pathlib.Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()
  return {int(x) for x in text.split()} if text else set()
 def reap_all_owned():
  deadline=time.monotonic()+15;events=[];errors=[]
  while time.monotonic()<deadline:
   owned=children()
   if not owned:return {'childrenRemaining':[],'events':events,'errors':errors}
   for pid in sorted(owned):
    fd=None
    try:
     waited,status=os.waitpid(pid,os.WNOHANG)
     if waited:
      events.append({'pid':pid,'action':'reaped','waitStatus':status});continue
     fd=os.pidfd_open(pid,0)
     # Check that this pid remains our direct child after opening the pidfd.
     if pid not in children():raise RuntimeError('child ownership changed')
     signal.pidfd_send_signal(fd,signal.SIGKILL)
     events.append({'pid':pid,'action':'pidfd-sigkill'})
    except (ProcessLookupError,ChildProcessError):events.append({'pid':pid,'action':'already-gone'})
    except BaseException as exc:errors.append(type(exc).__name__+': '+str(exc))
    finally:
     if fd is not None:os.close(fd)
   time.sleep(0.02)
  return {'childrenRemaining':sorted(children()),'events':events,'errors':errors}
 if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal') or children():raise RuntimeError('supervisor preconditions unavailable')
 orphan_result=None
 try:
  orphan_result=perform('orphan',"import json,os,subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); print(json.dumps({'pid':p.pid,'pgid':os.getpgrp()}),flush=True)",'UNKNOWN')
  assert orphan_result['unexpectedLeftoverGroup'] and orphan_result['forcedCleanup']
 finally:
  cleanup=reap_all_owned()
  print(json.dumps({'event':'synthetic-supervisor-custody','cleanup':cleanup,'runnerGroupGone':orphan_result.get('processGroupGone') if orphan_result else None}),flush=True)
 if cleanup['childrenRemaining'] or cleanup['errors']:raise RuntimeError('supervisor cleanup incomplete')
 (r.ROOT/'collision.stdout').write_text('preexisting-sentinel')
 x=perform('collision',"raise SystemExit('should never run')",'UNKNOWN')
 assert x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
 assert (r.ROOT/'collision.stdout').read_text()=='preexisting-sentinel'
 # A directory at the output path exercises an exclusive-open failure.
 (r.ROOT/'output-error.stdout').mkdir()
 x=perform('output-error',"raise SystemExit('should never run')",'UNKNOWN')
 assert x['errors'] and x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
print('PASS: synthetic success, timeout partial, signal, orphan group, collision and output-open failure')
