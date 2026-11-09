"""UNRUN OFFLINE DRAFT: extract only a previously verified output archive."""
import argparse,hashlib,json,pathlib,tarfile
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
 receipt=json.loads(a.receipt.read_bytes())
 if receipt.get('status')!='REASSEMBLED' or receipt.get('archiveSHA256')!=a.archive_sha256 or digest(a.archive)!=a.archive_sha256:raise RuntimeError('archive identity')
 a.output.mkdir(mode=0o700);seen=set();total=0
 with tarfile.open(a.archive,'r:gz') as tar:
  for m in tar:
   parts=m.name.split('/')
   if m.name in seen or len(seen)>=MAX_MEMBERS or any(x in ('','.','..') for x in parts) or not m.isfile() or not 0<=m.size<=200000000:raise RuntimeError('unsafe member')
   seen.add(m.name);total+=m.size
   if total>MAX_EXPANDED:raise RuntimeError('expanded size bound')
   if not m.name.startswith('output/'):continue
   path=a.output.joinpath(*parts[1:]);path.parent.mkdir(parents=True,exist_ok=True)
   remaining=m.size
   with path.open('xb') as out:
    src=tar.extractfile(m)
    while remaining:
     data=src.read(min(1048576,remaining))
     if not data:raise RuntimeError('truncated member')
     out.write(data);remaining-=len(data)
 if digest(a.archive)!=a.archive_sha256:raise RuntimeError('archive changed during extraction')
 print(json.dumps({'status':'EXTRACTED','archiveSHA256':a.archive_sha256,'files':len([x for x in seen if x.startswith('output/')]),'scope':'fresh output directory only; output still requires reviewed generated import'}))
if __name__=='__main__':main()
