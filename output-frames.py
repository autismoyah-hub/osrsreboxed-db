"""UNRUN TRANSPORT DRAFT: no provider authority; do not invoke yet.

Emit one bounded, independently reassemblable stream of the exact generated
output files, result metadata and complete data/docs hash manifest. All
provider/log limits and collector custody require case-specific review.
"""
import base64,gzip,hashlib,json,pathlib,sys,tarfile

ROOT=pathlib.Path('/tmp/slug-export-qualification')
ONE=ROOT/'one'
FILES=('docs/npc-dialogues.json','docs/npc-dialogues-minified.json','docs/event-dialogues.json','docs/npc-dialogue-index.json','docs/dialogue-types.json','docs/dialogue-manifest.json','data/dialogues/inferred-actions.txt','data/dialogues/authoring-index.json','data/dialogues/review-issues.json')
LOGS=tuple(label+'.'+ext for label in ('install','dependency-check','regression','export-one','export-two') for ext in ('stdout','stderr','result.json'))
MAX_ARCHIVE=32*1024*1024
CHUNK=3072

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 files=[]
 for name in FILES:
  p=ONE/name
  if p.is_symlink() or not p.is_file():raise RuntimeError('missing or nonregular required output '+name)
  files.append(('output/'+name,p))
 shards=ONE/'docs/dialogues'
 if shards.is_symlink() or not shards.is_dir():raise RuntimeError('missing shards')
 for p in sorted(shards.rglob('*')):
  if p.is_symlink():raise RuntimeError('symlink shard')
  if p.is_dir():continue
  if not p.is_file():raise RuntimeError('nonregular shard')
  files.append(('output/'+p.relative_to(ONE).as_posix(),p))
 for name in ('comparison.json','data-docs-manifest.json')+LOGS:
  p=ROOT/name
  if p.is_symlink() or not p.is_file():raise RuntimeError('missing retained result '+name)
  files.append(('evidence/'+name,p))
 names=[x for x,_ in files]
 if len(set(names))!=len(names):raise RuntimeError('duplicate archive name')
 path=ROOT/'qualified-output.tar.gz'
 with path.open('xb') as raw:
  with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as gz:
   with tarfile.open(fileobj=gz,mode='w|') as tar:
    for name,p in sorted(files):
     info=tarfile.TarInfo(name);info.size=p.stat().st_size;info.mode=0o644;info.mtime=0;info.uid=info.gid=0;info.uname=info.gname=''
     with p.open('rb') as source:tar.addfile(info,source)
 size=path.stat().st_size
 if not 0<size<=MAX_ARCHIVE:raise RuntimeError('archive exceeds reviewed draft cap')
 digest=hashlib.sha256()
 with path.open('rb') as f:
  while True:
   part=f.read(1048576)
   if not part:break
   digest.update(part)
 whole=digest.hexdigest();total=(size+CHUNK-1)//CHUNK
 print(json.dumps({'event':'slug-output-start','version':1,'bytes':size,'sha256':whole,'chunks':total,'members':len(files)},sort_keys=True),flush=True)
 with path.open('rb') as f:
  for i in range(total):
   part=f.read(CHUNK)
   if not part:raise RuntimeError('archive truncated during framing')
   print(json.dumps({'event':'slug-output-chunk','version':1,'index':i,'bytes':len(part),'sha256':sha(part),'base64':base64.b64encode(part).decode()},sort_keys=True),flush=True)
  if f.read(1):raise RuntimeError('archive changed during framing')
 print(json.dumps({'event':'slug-output-end','version':1,'bytes':size,'sha256':whole,'chunks':total},sort_keys=True),flush=True)

if __name__=='__main__':main()
