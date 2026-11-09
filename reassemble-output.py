"""UNRUN OFFLINE DRAFT: reassemble retained log frames; not a provider collector."""
import argparse,base64,hashlib,json,pathlib,re,tarfile
MAX=32*1024*1024
MAX_RAW=128*1024*1024
MAX_LINE=64*1024
MAX_EXPANDED=1024*1024*1024
MAX_MEMBERS=150000
MAX_META=16*1024*1024
CHUNK=3072
FILES={'docs/npc-dialogues.json','docs/npc-dialogues-minified.json','docs/event-dialogues.json','docs/npc-dialogue-index.json','docs/dialogue-types.json','docs/dialogue-manifest.json','data/dialogues/inferred-actions.txt','data/dialogues/authoring-index.json','data/dialogues/review-issues.json'}
LABELS=('install','dependency-check','regression','export-one','export-two')
LOGS={label+'.'+ext for label in LABELS for ext in ('stdout','stderr','result.json')}
def sha(b):return hashlib.sha256(b).hexdigest()
def file_sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while True:
   b=f.read(1048576)
   if not b:return h.hexdigest()
   h.update(b)
def unique(pairs):
 result={}
 for k,v in pairs:
  if k in result:raise ValueError('duplicate JSON key')
  result[k]=v
 return result
def parse(raw):return json.loads(raw,object_pairs_hook=unique)
def main():
 p=argparse.ArgumentParser();p.add_argument('raw',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);p.add_argument('commands',type=pathlib.Path);p.add_argument('commands_sha256');a=p.parse_args()
 if a.raw.stat().st_size>MAX_RAW:raise RuntimeError('raw input bound')
 command_bytes=a.commands.read_bytes()
 if sha(command_bytes)!=a.commands_sha256:raise RuntimeError('command plan identity')
 commands=parse(command_bytes)
 if set(commands)!=set(LABELS)|{'frame'}:raise RuntimeError('command plan labels')
 raw_identity=file_sha(a.raw)
 a.output.mkdir(mode=0o700);start=end=frame_result=relay=None;chunks={};raw_bytes=decoded=frame_bytes=0;frame_hash=hashlib.sha256()
 with a.raw.open('rb') as f:
  while True:
   raw=f.readline(MAX_LINE+1)
   if not raw:break
   raw_bytes+=len(raw)
   if len(raw)>MAX_LINE or raw_bytes>MAX_RAW:raise RuntimeError('raw input bound')
   try:row=parse(raw)
   except (ValueError,UnicodeDecodeError):
    if b'slug-output-' in raw:raise RuntimeError('malformed frame')
    continue
   if not isinstance(row,dict):continue
   event=row.get('event')
   if event=='command-result' and isinstance(row.get('result'),dict) and row['result'].get('label')=='frame':
    if frame_result is not None or start is not None:raise RuntimeError('duplicate or late frame result')
    frame_result=row['result']
   elif event=='frame-relay-complete':
    if end is None or relay is not None:raise RuntimeError('relay order')
    relay=row
   if isinstance(event,str) and event in ('slug-output-start','slug-output-chunk','slug-output-end'):
    frame_hash.update(raw);frame_bytes+=len(raw)
   if event=='slug-output-start':
    if start is not None or end is not None or row.get('version')!=1:raise RuntimeError('duplicate or invalid start')
    size=row.get('bytes');count=row.get('chunks');member_count=row.get('members');digest=row.get('sha256')
    if type(size)!=int or not 0<size<=MAX or type(count)!=int or count!=(size+CHUNK-1)//CHUNK or type(member_count)!=int or not 1<=member_count<=MAX_MEMBERS or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise RuntimeError('invalid start bounds')
    start=row
   elif event=='slug-output-chunk':
    if start is None or end is not None or row.get('version')!=1:raise RuntimeError('frame order')
    i=row.get('index')
    if type(i)!=int or not 0<=i<start['chunks'] or i in chunks:raise RuntimeError('frame index')
    encoded=row.get('base64')
    if not isinstance(encoded,str) or len(encoded)>4*((CHUNK+2)//3):raise RuntimeError('encoded frame bound')
    data=base64.b64decode(encoded,validate=True);expected=CHUNK if i<start['chunks']-1 else start['bytes']-CHUNK*(start['chunks']-1)
    if len(data)!=expected or len(data)!=row.get('bytes') or sha(data)!=row.get('sha256'):raise RuntimeError('invalid frame')
    decoded+=len(data)
    if decoded>start['bytes'] or decoded>MAX:raise RuntimeError('decoded frame bound')
    chunks[i]=data
   elif event=='slug-output-end':
    if start is None or end is not None or row.get('version')!=1:raise RuntimeError('end order')
    end=row
   elif isinstance(event,str) and event.startswith('slug-output-'):raise RuntimeError('unknown frame event')
 if file_sha(a.raw)!=raw_identity:raise RuntimeError('raw changed during read')
 if not start or not end or not frame_result or not relay:raise RuntimeError('incomplete stream')
 if frame_result.get('argv')!=commands['frame'] or frame_result.get('status')!='COMPLETE' or frame_result.get('exit')!=0 or frame_result.get('timedOut') is not False or frame_result.get('processGroupGone') is not True or frame_result.get('unexpectedLeftoverGroup') is not False or frame_result.get('forcedCleanup') is not False or frame_result.get('signal') is not None or frame_result.get('errors')!=[]:raise RuntimeError('frame producer incomplete')
 if frame_result.get('stderr',{}).get('bytes')!=0 or frame_result.get('stderr',{}).get('sha256')!=sha(b''):raise RuntimeError('frame producer stderr')
 if frame_result.get('stdout',{}).get('sha256')!=frame_hash.hexdigest() or frame_result.get('stdout',{}).get('bytes')!=frame_bytes or relay.get('sha256')!=frame_hash.hexdigest() or relay.get('bytes')!=frame_bytes:raise RuntimeError('frame producer identity mismatch')
 if set(chunks)!=set(range(start['chunks'])) or any(end.get(k)!=start.get(k) for k in ('chunks','bytes','sha256')):raise RuntimeError('end or frame mismatch')
 data=b''.join(chunks[i] for i in range(start['chunks']))
 if len(data)!=start['bytes'] or sha(data)!=start['sha256']:raise RuntimeError('archive identity')
 path=a.output/'qualified-output.tar.gz'
 with path.open('xb') as f:f.write(data)
 members={};metadata={};total=0
 with tarfile.open(path,'r:gz') as tar:
  for item in tar:
   name=item.name;parts=name.split('/')
   if name in members or len(members)>=MAX_MEMBERS or any(x in ('','.','..') for x in parts) or not item.isfile() or not 0<=item.size<=200000000:raise RuntimeError('unsafe tar member')
   total+=item.size
   if total>MAX_EXPANDED:raise RuntimeError('expanded size bound')
   ismeta=name in ('evidence/before-data-docs-manifest.json','evidence/first-data-docs-manifest.json','evidence/second-data-docs-manifest.json','evidence/comparison.json') or (name.startswith('evidence/') and name.endswith('.result.json'))
   if ismeta and item.size>MAX_META:raise RuntimeError('metadata size bound')
   source=tar.extractfile(item);h=hashlib.sha256();remaining=item.size;parts=[]
   while remaining:
    block=source.read(min(1048576,remaining))
    if not block:raise RuntimeError('truncated member')
    h.update(block);remaining-=len(block)
    if ismeta:parts.append(block)
   members[name]={'bytes':item.size,'sha256':h.hexdigest()}
   if ismeta:metadata[name]=parse(b''.join(parts))
 if len(members)!=start['members']:raise RuntimeError('member count')
 before=metadata['evidence/before-data-docs-manifest.json'];manifest=metadata['evidence/first-data-docs-manifest.json'];second=metadata['evidence/second-data-docs-manifest.json'];comparison=metadata['evidence/comparison.json']
 changed={k:{'before':before.get(k),'after':manifest.get(k)} for k in sorted(before.keys()|manifest.keys()) if before.get(k)!=manifest.get(k)}
 if manifest!=second or changed!=comparison.get('changed'):raise RuntimeError('complete manifest or changed-key mismatch')
 expected_outputs={k for k in manifest if k in FILES or k.startswith('docs/dialogues/')}
 expected={'output/'+k for k in expected_outputs}|{'evidence/comparison.json','evidence/before-data-docs-manifest.json','evidence/first-data-docs-manifest.json','evidence/second-data-docs-manifest.json'}|{'evidence/'+k for k in LOGS}
 if not FILES<=expected_outputs or set(members)!=expected:raise RuntimeError('output keyset mismatch')
 for k in expected_outputs:
  actual=members['output/'+k];want=manifest[k]
  if actual['sha256']!=want['sha256'] or actual['bytes']!=want['bytes']:raise RuntimeError('output hash mismatch '+k)
 if comparison.get('source')!='428591a413a55973e2fde1f7c479d34e64057edf' or comparison.get('dataDocsEqual') is not True or comparison.get('nonOutputSourceEqual') is not True or comparison.get('dataDocsFiles')!=len(manifest):raise RuntimeError('comparison not complete')
 for label in LABELS:
  record=metadata['evidence/'+label+'.result.json']
  if record.get('label')!=label or record.get('status')!='COMPLETE' or record.get('exit')!=0 or record.get('timedOut') is not False or record.get('processGroupGone') is not True or record.get('unexpectedLeftoverGroup') is not False or record.get('forcedCleanup') is not False or record.get('signal') is not None or record.get('argv')!=commands[label] or record.get('errors')!=[]:raise RuntimeError('command incomplete '+label)
  for stream in ('stdout','stderr'):
   got=members['evidence/'+label+'.'+stream];claim=record.get(stream,{})
   if got['sha256']!=claim.get('sha256') or got['bytes']!=claim.get('bytes'):raise RuntimeError('command log mismatch '+label)
 if file_sha(path)!=sha(data):raise RuntimeError('archive changed during inspection')
 result={'status':'REASSEMBLED','rawSHA256':raw_identity,'archiveSHA256':sha(data),'archiveBytes':len(data),'members':len(members),'expandedBytes':total,'commandsSHA256':a.commands_sha256,'outputFiles':{k:manifest[k] for k in sorted(expected_outputs)},'limit':'offline log reconstruction only; does not authenticate provider/custody or prove no omitted events outside this stream'}
 with (a.output/'reassembly.json').open('x') as f:json.dump(result,f,sort_keys=True);f.write('\n')
 print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
