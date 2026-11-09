"""UNRUN fake-only bucket proposal controls; no secret, network or SDK."""
import contextlib,importlib.util,io,json,pathlib,runpy,sys,types
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('proposal',HERE/'hf-bucket-readonly-proposal.py');adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
class API:
 def __init__(self):self.calls=[]
 def whoami(self,**kw):self.calls.append(('whoami',kw));return {'name':'Autismo-Yah'}
 def list_buckets(self,**kw):self.calls.append(('list_buckets',kw));return iter([])
api=adapter.ExplicitTokenApi(API,'synthetic-token')
assert api.whoami()['name']=='Autismo-Yah';assert list(api.list_buckets(namespace='Autismo-Yah'))==[]
assert all(row[1]['token']=='synthetic-token' for row in api._api.calls)
for name in ('run_job','bucket_info'):
 try:getattr(api,name)()
 except adapter.AccessError as e:assert e.code=='UNREVIEWED_HF_METHOD'
 else:raise AssertionError('unreviewed method exposed')
try:api.whoami(token='different-synthetic-token')
except adapter.AccessError as e:assert e.code=='AUTHORIZATION_SUBSTITUTION_REJECTED'
else:raise AssertionError('token substitution accepted')
class Fake:
 rows=[]
 def whoami(self):return {'name':'Autismo-Yah'}
 def list_buckets(self,namespace):assert namespace=='Autismo-Yah';return iter(self.rows)
def run(rows,ok):
 Fake.rows=rows;sys.modules['huggingface_hub']=types.SimpleNamespace(HfApi=Fake);out=io.StringIO()
 try:
  with contextlib.redirect_stdout(out):
   try:runpy.run_path(str(HERE/'bucket-list-proposal.py'),run_name='__main__')
   except RuntimeError:
    if ok:raise
   else:
    if not ok:raise AssertionError('invalid list accepted')
  if ok:assert json.loads(out.getvalue())['count']==len(rows)
 finally:sys.modules.pop('huggingface_hub',None)
run([],True);run([types.SimpleNamespace(id='Autismo-Yah/synthetic')],True)
run([types.SimpleNamespace(id='other/synthetic')],False)
run([types.SimpleNamespace(id='Autismo-Yah/synthetic')]*2,False)
run([types.SimpleNamespace(id='Autismo-Yah/item'+str(i)) for i in range(100)],True)
run([types.SimpleNamespace(id='Autismo-Yah/item'+str(i)) for i in range(101)],False)
print('PASS: synthetic token injection/substitution, method refusal and 100/101 listing boundary')
