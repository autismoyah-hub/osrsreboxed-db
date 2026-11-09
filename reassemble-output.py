"""UNRUN OFFLINE DRAFT: reassemble retained log frames; not a provider collector."""
import argparse,base64,hashlib,json,pathlib,tarfile
MAX=32*1024*1024
CHUNK=3072
FILES={'docs/npc-dialogues.json','docs/npc-dialogues-minified.json','docs/event-dialogues.json','docs/npc-dialogue-index.json','docs/dialogue-types.json','docs/dialogue-manifest.json','data/dialogues/inferred-actions.txt','data/dialogues/authoring-index.json','data/dialogues/review-issues.json'}
LOGS={label+'.'+ext for label in ('install','dependency-check','regression','export-one','export-two') for ext in ('stdout','stderr','result.json')}
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('raw',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);a=p.parse_args()
 a.output.mkdir(mode=0o700);start=end=None;chunks={}
 with a.raw.open('rb') as f:
  for raw in f:
   try:row=json.loads(raw)
   except (ValueError,UnicodeDecodeError):
    if b'slug-output-' in raw:raise RuntimeError('malformed frame')
    continue
   if not isinstance(row,dict):continue
   event=row.get('event')
   if event=='slug-output-start':
    if start is not None or end is not None:raise RuntimeError('duplicate start')
    start=row
   elif event=='slug-output-chunk':
    if start is None or end is not None or row.get('version')!=1:raise RuntimeError('frame order')
    i=row.get('index');data=base64.b64decode(row.get('base64',''),validate=True)
    if type(i)!=int or i<0 or i in chunks or len(data)!=row.get('bytes') or not 0<len(data)<=CHUNK or sha(data)!=row.get('sha256'):raise RuntimeError('invalid frame')
    chunks[i]=data
   elif event=='slug-output-end':
    if start is None or end is not None:raise RuntimeError('end order')
    end=row
 if not start or not end or start.get('version')!=1 or end.get('version')!=1:raise RuntimeError('incomplete stream')
 count=start.get('chunks');size=start.get('bytes')
 if type(size)!=int or not 0<size<=MAX or type(count)!=int or count!=(size+CHUNK-1)//CHUNK or set(chunks)!=set(range(count)):raise RuntimeError('frame count')
 if any(end.get(k)!=start.get(k) for k in ('chunks','bytes','sha256')):raise RuntimeError('end mismatch')
 data=b''.join(chunks[i] for i in range(count))
 if len(data)!=size or sha(data)!=start.get('sha256'):raise RuntimeError('archive identity')
 path=a.output/'qualified-output.tar.gz';path.write_bytes(data)
 members={};total=0
 with tarfile.open(path,'r:gz') as tar:
  for item in tar:
   name=item.name;parts=name.split('/')
   if name in members or any(x in ('','.','..') for x in parts) or not item.isfile() or item.size>200000000:raise RuntimeError('unsafe tar member')
   total+=item.size
   if total>1000000000:raise RuntimeError('expanded size bound')
   content=tar.extractfile(item).read();members[name]={'bytes':len(content),'sha256':sha(content)}
   if name in ('evidence/data-docs-manifest.json','evidence/comparison.json'):members[name]['parsed']=json.loads(content)
 if len(members)!=start.get('members'):raise RuntimeError('member count')
 manifest=members['evidence/data-docs-manifest.json']['parsed'];comparison=members['evidence/comparison.json']['parsed']
 expected_outputs={k for k in manifest if k in FILES or k.startswith('docs/dialogues/')}
 expected={'output/'+k for k in expected_outputs}|{'evidence/comparison.json','evidence/data-docs-manifest.json'}|{'evidence/'+k for k in LOGS}
 if not FILES<=expected_outputs or set(members)!=expected:raise RuntimeError('output keyset mismatch')
 for k in expected_outputs:
  actual=members['output/'+k];want=manifest[k]
  if actual['sha256']!=want['sha256'] or actual['bytes']!=want['bytes']:raise RuntimeError('output hash mismatch '+k)
 if comparison.get('dataDocsEqual') is not True or comparison.get('nonOutputSourceEqual') is not True:raise RuntimeError('comparison not complete')
 result={'status':'REASSEMBLED','archiveSHA256':sha(data),'archiveBytes':len(data),'members':len(members),'expandedBytes':total,'limit':'offline log reconstruction only; does not authenticate provider/custody or prove no omitted events outside this stream'}
 (a.output/'reassembly.json').write_text(json.dumps(result,sort_keys=True)+'\n');print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
