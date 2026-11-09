"""UNRUN staged input draft; no provider submission authority."""
import hashlib,os,pathlib,sys,urllib.request
BASE='https://raw.githubusercontent.com/autismoyah-hub/osrsreboxed-db/b994cad2b39539293c3a31ec9bfba4c8df4a46e5/'
INPUTS={
 'runner.py':(11696,'b4ca3792357dfb0b951806d3e18508f88bc300aa470872b96b09479f5628bc97'),
 'commands.json':(2040,'4e9e717a1f56f5ec9f88f7a826eb15e1a3fec3730f85175030b1d628b4b36292'),
 'wheels.json':(4531,'3507cb7213863d82ae3a36f3324917f58a10f770f1fafa53a0ea19660fa2440d'),
 'source-tree.json':(7811710,'264768453a032098643a544dc342f33f7f2c661b61792582ce0deca9bb885a51'),
 'output-frames.py':(4657,'fb3726a93596bec86de6e20c601072ec193a4d6e6016d4dd62a931601ea30198'),
}
def main():
 if sys.executable!='/usr/local/bin/python3.9' or sys.version_info[:2]!=(3,9):raise RuntimeError('interpreter mismatch')
 root=pathlib.Path('/tmp/slug-case');os.umask(0o077);root.mkdir(mode=0o700)
 for name,(size,digest) in INPUTS.items():
  target=root/name;h=hashlib.sha256();count=0
  with urllib.request.urlopen(BASE+name,timeout=120) as response,target.open('xb') as out:
   while True:
    block=response.read(1048576)
    if not block:break
    count+=len(block)
    if count>size:raise RuntimeError('staged input exceeds bound')
    h.update(block);out.write(block)
   out.flush();os.fsync(out.fileno())
  if count!=size or h.hexdigest()!=digest:raise RuntimeError('staged input identity mismatch '+name)
 # Capture and verify the runner bytes again, then execute that exact snapshot.
 runner=(root/'runner.py').read_bytes()
 if len(runner)!=INPUTS['runner.py'][0] or hashlib.sha256(runner).hexdigest()!=INPUTS['runner.py'][1]:raise RuntimeError('runner snapshot mismatch')
 sys.argv=[str(root/'runner.py'),'--emit-reviewed-output']
 exec(compile(runner,str(root/'runner.py'),'exec'),{'__name__':'__main__','__file__':str(root/'runner.py')})
if __name__=='__main__':main()
