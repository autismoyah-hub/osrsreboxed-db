"""UNRUN synthetic controls for SDK string record capture only."""
import base64,contextlib,importlib.util,io,json,pathlib,tempfile
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sdk_records',HERE/'sdk-records.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Fake:
 def __init__(self,values,fail=False):self.values=values;self.fail=fail
 def fetch_job_logs(self,**kwargs):
  assert kwargs=={'job_id':'synthetic','namespace':'synthetic','follow':False}
  yield from self.values
  if self.fail:raise RuntimeError('synthetic iterator error')
def capture(root,name,values,fail=False):
 with contextlib.redirect_stdout(io.StringIO()):
  try:m.capture_records(Fake(values,fail),'synthetic','synthetic',root/name)
  except RuntimeError:pass
 return json.loads((root/name/'capture.json').read_text())
with tempfile.TemporaryDirectory(prefix='slug-sdk-records-') as tmp:
 root=pathlib.Path(tmp);values=['split',' frame','\n','double\n\n','', 'snowman \u2603'];x=capture(root,'ok',values)
 assert x['status']=='ITERATION_RETURNED' and x['records']==len(values)
 rows=[json.loads(x) for x in (root/'ok/records.jsonl').read_text().splitlines()]
 assert [base64.b64decode(x['base64']).decode('utf-8') for x in rows]==values
 x=capture(root,'iterator',['partial'],True);assert x['status']=='UNKNOWN' and x['errorType']=='RuntimeError' and x['records']==1
 old=m.MAX_TOTAL_BYTES;m.MAX_TOTAL_BYTES=2
 try:x=capture(root,'cap',['long']);assert x['status']=='UNKNOWN' and x['errorType']=='ValueError'
 finally:m.MAX_TOTAL_BYTES=old
 original=m.os.fsync;calls=[0]
 def fail_once(fd):
  calls[0]+=1
  if calls[0]==1:raise OSError('synthetic disk failure')
  return original(fd)
 m.os.fsync=fail_once
 try:x=capture(root,'disk',['partial']);assert x['status']=='UNKNOWN' and x['errorType']=='OSError'
 finally:m.os.fsync=original
print('PASS: synthetic exact SDK string boundaries, iterator error, cap and one fsync failure')
