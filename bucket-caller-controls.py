"""UNRUN fake caller controls: no child, SDK, secret, network, or provider."""
import contextlib,hashlib,importlib.util,io,json,os,pathlib,shutil,subprocess,sys,tempfile,types
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('bucket_caller',HERE/'bucket-discovery-caller.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(b):return hashlib.sha256(b).hexdigest()
class OSProxy:
 def __init__(self):self.fail_fsync=False;self.fail_pidfd=False;self.calls=0
 def __getattr__(self,k):return getattr(os,k)
 def pidfd_open(self,pid,flags):
  if self.fail_pidfd:raise OSError('synthetic pidfd failure')
  return 987654
 def close(self,fd):
  if fd!=987654:return os.close(fd)
 def fsync(self,fd):
  self.calls+=1
  if self.fail_fsync:raise OSError('synthetic fsync failure')
  return os.fsync(fd)
class SignalProxy:
 SIGKILL=m.signal.SIGKILL
 @staticmethod
 def pidfd_send_signal(fd,sig):assert fd==987654
class TimeProxy:
 def __init__(self):self.tick=0
 def monotonic(self):self.tick+=1;return self.tick
 def sleep(self,n):pass
class Snapshot:
 def __init__(self,root,scenario):self.root=root;self.scenario=scenario;self.calls=0;self.path=None
 def build(self,manifest):
  self.path=self.root/'fake-snapshot';self.path.mkdir();site=self.path/'site';site.mkdir();meta=site/'huggingface_hub-2.4.0.dist-info';meta.mkdir();(meta/'METADATA').write_text('Name: huggingface_hub\nVersion: 2.4.0\n\n');return self.path,site
 def verify(self,site,manifest):
  self.calls+=1
  if self.scenario=='sdk-mutation' and self.calls==2:raise RuntimeError('synthetic SDK mutation')
class ShutilProxy:
 def __init__(self):self.fail=False
 def rmtree(self,path):
  if self.fail:raise OSError('synthetic cleanup failure')
  return shutil.rmtree(path)
class FakeChild:
 def __init__(self,scenario,out):
  self.pid=555555;self.calls=0;self.scenario=scenario
  ids=[]
  if scenario=='hundred':ids=['Autismo-Yah/item'+str(i) for i in range(100)]
  if scenario=='over-limit':ids=['Autismo-Yah/item'+str(i) for i in range(101)]
  if scenario=='duplicate':ids=['Autismo-Yah/item','Autismo-Yah/item']
  if scenario=='wrong-id':ids=['other/item']
  payload={'status':'LIST_ITERATION_RETURNED','namespace':'wrong' if scenario=='wrong-namespace' else 'Autismo-Yah','count':len(ids),'ids':ids}
  if scenario=='malformed':out.write(b'{')
  elif scenario=='oversize':out.write(b'x'*(m.LIMIT+1))
  elif scenario=='timeout':out.write(b'synthetic partial')
  else:out.write(json.dumps(payload).encode())
 def wait(self,timeout):
  self.calls+=1
  if self.scenario=='timeout' and self.calls==1:raise subprocess.TimeoutExpired('synthetic',timeout)
  return -9 if self.scenario=='timeout' else 0

def main():
 original=(m.HERE,m.load,m.subprocess,m.os,m.signal,m.time,m.shutil,m.group_gone,sys.argv)
 with tempfile.TemporaryDirectory(prefix='slug-bucket-caller-controls-') as tmp:
  root=pathlib.Path(tmp);m.HERE=root;home=root/'discovery-runs';home.mkdir(mode=0o700)
  for name,_ in m.FILES.values():shutil.copyfile(HERE/name,root/name)
  meta=b'Name: huggingface_hub\nVersion: 2.4.0\n\n';rows=[{'path':'huggingface_hub-2.4.0.dist-info/METADATA','bytes':len(meta),'sha256':sha(meta)}]
  manifest=root/'sdk.json';manifest.write_text(json.dumps(rows));manifest_sha=sha(manifest.read_bytes())
  plan=root/'plan.json';plan_data={'owner':m.OWNER,'action':'READ_ONLY_BUCKET_LIST','sdkVersion':'2.4.0','sdkManifestSHA256':manifest_sha,'executionHold':None,'maxResults':100,'timeoutSeconds':120};plan.write_text(json.dumps(plan_data));plan_sha=sha(plan.read_bytes())
  proxy=OSProxy();shutil_proxy=ShutilProxy();m.os=proxy;m.signal=SignalProxy;m.time=TimeProxy();m.shutil=shutil_proxy
  class FakeSubprocess:
   TimeoutExpired=subprocess.TimeoutExpired
   def __init__(self):self.scenario=None;self.calls=0
   def Popen(self,cmd,stdout,stderr,**kwargs):
    self.calls+=1
    if self.scenario=='launch':raise OSError('synthetic launch failure')
    return FakeChild(self.scenario,stdout)
  fake=FakeSubprocess();m.subprocess=fake
  def run(name,scenario,expected,group=True,fail_fsync=False):
   fake.scenario=scenario;fake.calls=0;proxy.calls=0;proxy.fail_fsync=fail_fsync;proxy.fail_pidfd=scenario=='pidfd';shutil_proxy.fail=scenario=='cleanup';snapshot=Snapshot(root,scenario)
   m.load=lambda path,digest: snapshot if path.name=='bucket-sdk-snapshot.py' else types.SimpleNamespace(CHILD_BOOTSTRAP='synthetic')
   m.group_gone=lambda pid:group
   output=home/name;sys.argv=['bucket-discovery-caller.py','--plan',str(plan),'--plan-sha256',plan_sha,'--sdk-manifest',str(manifest),'--output',str(output)]
   with contextlib.redirect_stdout(io.StringIO()):
    try:m.main()
    except BaseException:
     if expected=='ITERATION_RETURNED_METADATA_ONLY':raise
    else:
     if expected!='ITERATION_RETURNED_METADATA_ONLY':raise AssertionError('failure accepted')
   receipt=output/'receipt.json'
   if fail_fsync:
    assert not receipt.exists() and proxy.calls==1 and fake.calls==0
   else:
    assert receipt.is_file() and fake.calls==1,'missing receipt or child launch';x=json.loads(receipt.read_text());assert x['status']==expected,(scenario,x)
    if scenario in ('over-limit','duplicate','wrong-id','wrong-namespace'):
     assert 'RuntimeError' in x['errors'] and x.get('sdkPrePost')=='MATCH'
    if scenario=='malformed':assert 'JSONDecodeError' in x['errors'] and x.get('sdkPrePost')=='MATCH'
    if scenario=='timeout':assert x['timedOut'] and x['exit']==-9 and x['stdout.private']['sha256']==sha(b'synthetic partial')
    if scenario=='leftover':assert x['processGroupGone'] is False and x['snapshotDisposition']=='PRESERVED_PENDING_CLOSURE' and snapshot.path.exists()
    if scenario=='pidfd':assert x['pid']==555555 and 'OSError' in x['errors']
    if scenario=='launch':assert x['pid'] is None and 'OSError' in x['errors']
    if scenario=='sdk-mutation':assert 'RuntimeError' in x['errors'] and snapshot.calls==2
    if scenario=='cleanup':assert any(y.startswith('snapshot cleanup ') for y in x['errors']) and snapshot.path.exists()
    if scenario=='oversize':assert any(y.startswith('capture read ') for y in x['errors'])
    if scenario=='hundred':assert x['count']==100
   proxy.fail_fsync=False;proxy.fail_pidfd=False;shutil_proxy.fail=False
   if snapshot.path and snapshot.path.exists():shutil.rmtree(snapshot.path)
  try:
   run('empty','empty','ITERATION_RETURNED_METADATA_ONLY');run('hundred','hundred','ITERATION_RETURNED_METADATA_ONLY')
   for n in ('over-limit','duplicate','wrong-id','wrong-namespace','malformed','timeout','oversize','launch','pidfd','sdk-mutation','cleanup'):run(n,n,'UNKNOWN')
   run('leftover','leftover','UNKNOWN',group=False);run('fsync','fsync','UNKNOWN',fail_fsync=True)
  finally:m.HERE,m.load,m.subprocess,m.os,m.signal,m.time,m.shutil,m.group_gone,sys.argv=original
 print('PASS: synthetic caller identity, limits, malformed, timeout, closure, SDK and capture failures')
if __name__=='__main__':main()
