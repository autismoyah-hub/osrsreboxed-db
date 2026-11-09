"""UNRUN synthetic supervisor controls. Fake child only; no SDK/provider/network."""
import contextlib,hashlib,importlib.util,io,json,os,pathlib,subprocess,sys,tempfile,types
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('bucket_supervisor',HERE/'bucket-discovery-supervisor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(b):return hashlib.sha256(b).hexdigest()
class OSProxy:
 def __init__(self,real):self.real=real;self.fail_pidfd=False;self.fail_fsync=False
 def __getattr__(self,k):return getattr(self.real,k)
 def pidfd_open(self,pid,flags):
  if self.fail_pidfd:raise OSError('synthetic pidfd failure')
  return 987654
 def close(self,fd):
  if fd!=987654:return self.real.close(fd)
 def fsync(self,fd):
  if self.fail_fsync:raise OSError('synthetic fsync failure')
  return self.real.fsync(fd)
class SignalProxy:
 SIGKILL=m.signal.SIGKILL
 @staticmethod
 def pidfd_send_signal(fd,sig):assert fd==987654
class FakeChild:
 def __init__(self,scenario,stdout,stderr,plan,snaproot):
  self.scenario=scenario;self.pid=555555;self.calls=0;self.plan=plan
  if scenario=='partial-timeout':stdout.write(b'synthetic partial')
  if scenario=='oversize':stdout.write(b'x'*(m.LIMIT+1))
  if scenario=='nested-escape':(snaproot/'possible-nested-snapshot').mkdir(exist_ok=True)
 def wait(self,timeout):
  self.calls+=1
  if self.scenario in ('partial-timeout','nested-escape') and self.calls==1:raise subprocess.TimeoutExpired('synthetic',timeout)
  if self.scenario=='mutation':self.plan.write_text('{"changed":true}')
  return -9 if self.scenario in ('partial-timeout','nested-escape') else 0

def main():
 proxy=OSProxy(os);original_os=m.os;original_signal=m.signal;original_popen=m.subprocess.Popen;original_group=m.group_gone;oldargv=sys.argv
 with tempfile.TemporaryDirectory(prefix='slug-bucket-supervisor-control-') as tmp:
  root=pathlib.Path(tmp);m.HERE=root;m.SNAPROOT=root/'snapshots';m.SNAPROOT.mkdir(mode=0o700);(root/'supervisor-runs').mkdir(mode=0o700)
  caller=root/'bucket-discovery-caller.py';caller.write_text('# synthetic caller\n');m.CALLER_SHA=sha(caller.read_bytes())
  manifest=root/'sdk.json';manifest.write_text('[]');manifest_sha=sha(manifest.read_bytes());plan=root/'plan.json';plan_data=json.dumps({'sdkManifestSHA256':manifest_sha});plan.write_text(plan_data)
  m.os=proxy;m.signal=SignalProxy
  def run(name,scenario,expect,group=True):
   plan.write_text(plan_data);plan_sha=sha(plan.read_bytes());output=root/'supervisor-runs'/name
   def popen(cmd,stdout,stderr,**kw):
    if scenario=='launch':raise OSError('synthetic launch error')
    return FakeChild(scenario,stdout,stderr,plan,m.SNAPROOT)
   m.subprocess.Popen=popen;m.group_gone=lambda pid:group;proxy.fail_pidfd=scenario=='pidfd';proxy.fail_fsync=scenario=='fsync'
   sys.argv=['bucket-discovery-supervisor.py','--plan',str(plan),'--plan-sha256',plan_sha,'--sdk-manifest',str(manifest),'--sdk-manifest-sha256',manifest_sha,'--caller-output',str(root/'unused'), '--output',str(output)]
   with contextlib.redirect_stdout(io.StringIO()):
    try:m.main()
    except BaseException:
     if expect=='CALLER_EXITED_ZERO_AWAIT_RECEIPT_REVIEW':raise
    else:
     if expect!='CALLER_EXITED_ZERO_AWAIT_RECEIPT_REVIEW':raise AssertionError('failure accepted')
   receipt=output/'receipt.json'
   if receipt.exists():
    x=json.loads(receipt.read_text());assert x['status']==expect,(name,x)
    assert x['nestedAuthAction']=='POSSIBLY_ACTIVE_UNTIL_INDEPENDENT_RECONCILIATION'
   else:assert expect=='UNKNOWN'
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
   run('fsync','fsync','UNKNOWN')
  finally:
   m.os=original_os;m.signal=original_signal;m.subprocess.Popen=original_popen;m.group_gone=original_group;sys.argv=oldargv
 print('PASS: synthetic supervisor success, timeout/nested hold, leftover, size, launch, pidfd, mutation and fsync failure')
if __name__=='__main__':main()
