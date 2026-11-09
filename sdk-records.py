"""UNRUN collection helper draft; no authentication, lock or provider admission.

Preserves exactly the Unicode strings returned by the SDK as base64 UTF-8
records with indexes. It deliberately makes no claim about producer byte
boundaries, SDK completeness, terminal state, or reconstruction policy.
Caller must independently bind identity, sole custody and a bounded child.
"""
import base64,hashlib,json,os,pathlib,time
MAX_RECORDS=200000
MAX_RECORD_BYTES=16*1024*1024
MAX_TOTAL_BYTES=128*1024*1024

def capture_records(api,namespace,job_id,directory):
 root=pathlib.Path(directory);root.mkdir(mode=0o700)
 started=time.monotonic();count=total=0;digest=hashlib.sha256();status='UNKNOWN';error=None
 try:
  with (root/'records.jsonl').open('xb') as out:
   for value in api.fetch_job_logs(job_id=job_id,namespace=namespace,follow=False):
    if type(value) is not str:raise TypeError('SDK record is not a string')
    if len(value)>MAX_RECORD_BYTES:raise ValueError('record character bound')
    raw=value.encode('utf-8','strict')
    if len(raw)>MAX_RECORD_BYTES or count>=MAX_RECORDS or total+len(raw)>MAX_TOTAL_BYTES:raise ValueError('record bound')
    row={'index':count,'encoding':'utf-8','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode('ascii')}
    encoded=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')
    out.write(encoded);out.flush();os.fsync(out.fileno());digest.update(encoded);count+=1;total+=len(raw)
  status='ITERATION_RETURNED'
 except BaseException as exc:
  error=type(exc).__name__
 finally:
  actual_sha=None;actual_bytes=None
  try:
   path=root/'records.jsonl'
   if path.exists():
    actual_bytes=path.stat().st_size;h=hashlib.sha256()
    with path.open('rb') as f:
     while True:
      block=f.read(1048576)
      if not block:break
      h.update(block)
    actual_sha=h.hexdigest()
  except BaseException:
   status='UNKNOWN';error=error or 'RecordFileReadError'
  if status=='ITERATION_RETURNED' and actual_sha!=digest.hexdigest():status='UNKNOWN';error='RecordFileMismatch'
  receipt={'event':'sdk-record-capture','namespace':namespace,'jobId':job_id,'status':status,'errorType':error,'records':count,'utf8Bytes':total,'completedRecordWritesSHA256':digest.hexdigest(),'actualRecordFileSHA256':actual_sha,'actualRecordFileBytes':actual_bytes,'elapsedSeconds':round(time.monotonic()-started,3),'scope':'SDK-returned strings only; no producer-byte, provider completeness, terminal or custody proof'}
  with (root/'capture.json').open('x',encoding='utf-8') as f:
   json.dump(receipt,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
  print(json.dumps(receipt,sort_keys=True),flush=True)
 if status!='ITERATION_RETURNED':raise RuntimeError('capture incomplete; no retry')
 return receipt
