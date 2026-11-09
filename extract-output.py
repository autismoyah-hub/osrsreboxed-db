"""UNRUN OFFLINE DRAFT: extract a reviewed, independently verified archive."""
import argparse,hashlib,json,os,pathlib,stat,tarfile
MAX_EXPANDED=1024*1024*1024
MAX_MEMBERS=150000
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while True:
   b=f.read(1048576)
   if not b:return h.hexdigest()
   h.update(b)
def main():
 p=argparse.ArgumentParser();p.add_argument('archive',type=pathlib.Path);p.add_argument('archive_sha256');p.add_argument('receipt',type=pathlib.Path);p.add_argument('receipt_sha256');p.add_argument('output',type=pathlib.Path);a=p.parse_args()
 if digest(a.receipt)!=a.receipt_sha256:raise RuntimeError('receipt identity')
 receipt=json.loads(a.receipt.read_bytes());expected=receipt.get('outputFiles')
 if receipt.get('status')!='REASSEMBLED' or not isinstance(expected,dict) or receipt.get('archiveSHA256')!=a.archive_sha256 or digest(a.archive)!=a.archive_sha256:raise RuntimeError('archive identity')
 a.output.mkdir(mode=0o700);seen=set();written=set();total=0
 with tarfile.open(a.archive,'r:gz') as tar:
  for m in tar:
   parts=m.name.split('/')
   if m.name in seen or len(seen)>=MAX_MEMBERS or any(x in ('','.','..') for x in parts) or not m.isfile() or not 0<=m.size<=200000000:raise RuntimeError('unsafe member')
   seen.add(m.name);total+=m.size
   if total>MAX_EXPANDED:raise RuntimeError('expanded size bound')
   if not m.name.startswith('output/'):continue
   rel='/'.join(parts[1:]);want=expected.get(rel)
   if not isinstance(want,dict) or want.get('bytes')!=m.size or want.get('mode') not in ('100644','100755'):raise RuntimeError('unexpected output')
   path=a.output.joinpath(*parts[1:]);path.parent.mkdir(parents=True,exist_ok=True)
   for parent in (path.parent,*path.parent.parents):
    if parent==a.output.parent:break
    if parent.is_symlink() or not parent.is_dir():raise RuntimeError('unsafe output parent')
   remaining=m.size;h=hashlib.sha256()
   fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'wb') as out:
    src=tar.extractfile(m)
    while remaining:
     data=src.read(min(1048576,remaining))
     if not data:raise RuntimeError('truncated member')
     out.write(data);h.update(data);remaining-=len(data)
    out.flush();os.fchmod(out.fileno(),0o755 if want['mode']=='100755' else 0o644);os.fsync(out.fileno())
   if h.hexdigest()!=want['sha256'] or digest(path)!=want['sha256'] or path.stat().st_size!=want['bytes']:raise RuntimeError('output mismatch')
   written.add(rel)
 if written!=set(expected):raise RuntimeError('extracted output keyset mismatch')
 actual=set()
 for path in a.output.rglob('*'):
  if path.is_symlink():raise RuntimeError('symlink output')
  if path.is_dir():continue
  if not path.is_file():raise RuntimeError('nonregular output')
  rel=path.relative_to(a.output).as_posix();actual.add(rel);want=expected[rel]
  if digest(path)!=want['sha256'] or path.stat().st_size!=want['bytes'] or ('100755' if path.stat().st_mode&0o111 else '100644')!=want['mode']:raise RuntimeError('post-read output mismatch')
 if actual!=set(expected) or digest(a.archive)!=a.archive_sha256 or digest(a.receipt)!=a.receipt_sha256:raise RuntimeError('post-extraction identity')
 for directory in sorted((p for p in a.output.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
  fd=os.open(str(directory),os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 fd=os.open(str(a.output),os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 print(json.dumps({'status':'EXTRACTED','archiveSHA256':a.archive_sha256,'files':len(written),'scope':'fresh output directory only; no authenticated custody or reviewed generated import'}))
if __name__=='__main__':main()
