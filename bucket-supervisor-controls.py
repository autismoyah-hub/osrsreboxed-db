"""UNRUN synthetic supervisor controls. Fake child only; no SDK/provider/network."""
import contextlib,hashlib,importlib.util,io,json,os,pathlib,subprocess,sys,tempfile,types
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('bucket_supervisor',HERE/'bucket-discovery-supervisor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(b):return hashlib.sha256(b).hexdigest()
class OSProxy:
 def __init__(self,real):self.real=real;self.fail_pidfd=False;self.fail_fsync=False;self.fsync_calls=0;self.pidfd_calls=0
 def __getattr__(self,k):return getattr(self.real,k)
 def pidfd_open(self,pid,flags):
  self.pidfd_calls+=1
  if self.fail_pidfd:raise OSError('synthetic pidfd failure')
  return 987654
 def close(self,fd):
  if fd!=987654:return self.real.close(fd)
 def fsync(self,fd):
  self.fsync_calls+=1
  if self.fail_fsync:raise OSError('synthetic fsync failure')
  return self.real.fsync(fd)
class SignalProxy:
 SIGKILL=m.signal.SIGKILL
 @staticmethod
 def pidfd_send_signal(fd,sig):assert fd==987654
class FakeChild:
 def __init__(self,scenario,stdout,stderr,plan,snaproot,caller,manifest):
  self.scenario=scenario;self.pid=555555;self.calls=0;self.plan=plan;self.caller=caller;self.manifest=manifest
  if scenario=='partial-timeout':stdout.write(b'synthetic partial')
  if scenario=='oversize':stdout.write(b'x'*(m.LIMIT+1))
  if scenario=='nested-escape':(snaproot/'possible-nested-snapshot').mkdir(exist_ok=True)
 def wait(self,timeout):
  self.calls+=1
  if self.scenario in ('partial-timeout','nested-escape') and self.calls==1:raise subprocess.TimeoutExpired('synthetic',timeout)
  if self.scenario=='mutation':self.plan.write_text('{"changed":true}')
  if self.scenario=='caller-mutation':self.caller.write_text('# changed caller\n')
  if self.scenario=='manifest-mutation':self.manifest.write_text('[1]')
  return -9 if self.scenario in ('partial-timeout','nested-escape') else 0

def main():
 proxy=OSProxy(os);original_os=m.os;original_signal=m.signal;original_popen=m.subprocess.Popen;original_group=m.group_gone;oldargv=sys.argv
 with tempfile.TemporaryDirectory(prefix='slug-bucket-supervisor-control-') as tmp:
  root=pathlib.Path(tmp);m.HERE=root;m.SNAPROOT=root/'snapshots';m.SNAPROOT.mkdir(mode=0o700);(root/'supervisor-runs').mkdir(mode=0o700)
  caller=root/'bucket-discovery-caller.py';caller.write_text('# synthetic caller\n');m.CALLER_SHA=sha(caller.read_bytes())
  caller_data=caller.read_bytes();manifest=root/'sdk.json';manifest_data=b'[]';manifest.write_bytes(manifest_data);manifest_sha=sha(manifest_data);plan=root/'plan.json';plan_data=json.dumps({'sdkManifestSHA256':manifest_sha});plan.write_text(plan_data)
  m.os=proxy;m.signal=SignalProxy
  def run(name,scenario,expect,group=True):
   caller.write_bytes(caller_data);manifest.write_bytes(manifest_data);plan.write_text(plan_data);plan_sha=sha(plan.read_bytes());output=root/'supervisor-runs'/name;state={'launchCalls':0,'child':None};proxy.fsync_calls=0;proxy.pidfd_calls=0
   def popen(cmd,stdout,stderr,**kw):
    state['launchCalls']+=1
    if scenario=='launch':raise OSError('synthetic launch error')
    state['child']=FakeChild(scenario,stdout,stderr,plan,m.SNAPROOT,caller,manifest);return state['child']
   m.subprocess.Popen=popen;m.group_gone=lambda pid:group;proxy.fail_pidfd=scenario=='pidfd';proxy.fail_fsync=scenario=='fsync'
   sys.argv=['bucket-discovery-supervisor.py','--plan',str(plan),'--plan-sha256',plan_sha,'--sdk-manifest',str(manifest),'--sdk-manifest-sha256',manifest_sha,'--caller-output',str(root/'unused'), '--output',str(output)]
   with contextlib.redirect_stdout(io.StringIO()):
    try:m.main()
    except BaseException:
     if expect=='CALLER_EXITED_ZERO_AWAIT_RECEIPT_REVIEW':raise
    else:
     if expect!='CALLER_EXITED_ZERO_AWAIT_RECEIPT_REVIEW':raise AssertionError('failure accepted')
   receipt=output/'receipt.json'
   if scenario=='fsync':
    assert not receipt.exists() and proxy.fsync_calls==1 and state['launchCalls']==0
   else:
    assert receipt.is_file(),'expected receipt missing for '+name
    x=json.loads(receipt.read_text());assert x['status']==expect,(name,x)
    assert x['nestedAuthAction']=='POSSIBLY_ACTIVE_UNTIL_INDEPENDENT_RECONCILIATION'
    assert state['launchCalls']==1
    if scenario=='partial-timeout':
     assert x['timedOut'] and x['exit']==-9 and x['processGroupGone'] is True and x['stdout.private']['sha256']==sha(b'synthetic partial')
    elif scenario=='nested-escape':
     assert x['timedOut'] and x['exit']==-9 and x['processGroupGone'] is True and 'possible-nested-snapshot' in x['snapshotsAfter']
    elif name=='leftover':assert x['processGroupGone'] is False
    elif scenario=='oversize':assert 'capture read RuntimeError' in x['errors']
    elif scenario=='launch':assert x['pid'] is None and 'OSError' in x['errors']
    elif scenario=='pidfd':assert x['pid']==555555 and proxy.pidfd_calls==1 and 'OSError' in x['errors'] and x['processGroupGone'] is False
    elif scenario in ('mutation','caller-mutation','manifest-mutation'):assert 'RuntimeError' in x['errors'] and 'sourcePrePost' not in x
    elif scenario=='success':assert x['exit']==0 and x['processGroupGone'] is True and x['sourcePrePost']=='MATCH'
   proxy.fail_pidfd=False;proxy.fail_fsync=False
  try:
   run('success','success','CALLER_EXITED_ZERO_AWAIT_RECEIPT_REVIEW')
   run('timeout','partial-timeout','UNKNOWN')
   run('escape','nested-escape','UNKNOWN',group=True)
   assert (m.SNAPROOT/'possible-nested-snapshot').is_dir()
   run('leftover','success','UNKNOWN',group=False)
   run('oversize','oversize','UNKNOWN')
   run('launch','launch','UNKNOWN')
   run('pidfd','pidfd','UNKNOWN',group=False)
   run('mutation','mutation','UNKNOWN')
   run('caller-mutation','caller-mutation','UNKNOWN')
   run('manifest-mutation','manifest-mutation','UNKNOWN')
   run('fsync','fsync','UNKNOWN')
  finally:
   m.os=original_os;m.signal=original_signal;m.subprocess.Popen=original_popen;m.group_gone=original_group;sys.argv=oldargv
 print('PASS: synthetic supervisor success, timeout/nested hold, leftover, size, launch, pidfd, mutation and fsync failure')
if __name__=='__main__':main()
