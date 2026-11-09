"""UNRUN synthetic-only draft. No network, provider, GAME, source fetch or export."""
import importlib.util, json, os, pathlib, signal, sys, tempfile

spec=importlib.util.spec_from_file_location('slug_runner',pathlib.Path(__file__).with_name('runner.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8'}

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
 x=perform('orphan',"import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);print('leader done',flush=True)",'UNKNOWN')
 assert x['unexpectedLeftoverGroup'] and x['forcedCleanup']
 (r.ROOT/'collision.stdout').write_text('preexisting-sentinel')
 x=perform('collision',"raise SystemExit('should never run')",'UNKNOWN')
 assert x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
 assert (r.ROOT/'collision.stdout').read_text()=='preexisting-sentinel'
 # A directory at the output path exercises an exclusive-open failure.
 (r.ROOT/'output-error.stdout').mkdir()
 x=perform('output-error',"raise SystemExit('should never run')",'UNKNOWN')
 assert x['errors'] and x['stdout']=={'status':'PREEXISTING_COLLISION_NOT_CAPTURED'}
print('PASS: synthetic success, timeout partial, signal, orphan group, collision and output-open failure')
