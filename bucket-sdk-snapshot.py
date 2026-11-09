"""UNRUN SDK snapshot draft: bounded regular files and exact private manifest."""
from pathlib import Path
import hashlib,json,os,shutil,stat,tempfile
SOURCE=Path('/tmp/slug-hf-sdk/site-packages')
SNAPROOT=Path('/tmp/slug-bucket-snapshots')
MAX_FILE=32*1024*1024
MAX_TOTAL=512*1024*1024
MAX_FILES=10000

class SnapshotBuildError(RuntimeError):
 def __init__(self,path):self.snapshotPath=str(path);super().__init__('partial snapshot cleanup failed')

def expected_rows(manifest_path):
 rows=json.loads(Path(manifest_path).read_bytes())
 if not isinstance(rows,list) or not 0<len(rows)<=MAX_FILES:raise RuntimeError('SDK_MANIFEST_INVALID')
 seen=set();total=0
 for row in rows:
  if not isinstance(row,dict) or set(row)!={'path','bytes','sha256'}:raise RuntimeError('SDK_MANIFEST_INVALID')
  n=row['path'];parts=n.split('/') if isinstance(n,str) else []
  if not parts or any(x in ('','.','..') for x in parts) or n in seen or type(row['bytes']) is not int or not 0<=row['bytes']<=MAX_FILE or not isinstance(row['sha256'],str) or len(row['sha256'])!=64:raise RuntimeError('SDK_MANIFEST_INVALID')
  seen.add(n);total+=row['bytes']
  if total>MAX_TOTAL:raise RuntimeError('SDK_MANIFEST_SIZE_BOUND')
 if [x['path'] for x in rows]!=sorted(seen):raise RuntimeError('SDK_MANIFEST_ORDER')
 return rows

def open_regular(path,observed):
 flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
 fd=os.open(str(path),flags)
 try:
  actual=os.fstat(fd)
  if not stat.S_ISREG(actual.st_mode) or (actual.st_dev,actual.st_ino,actual.st_size)!=(observed.st_dev,observed.st_ino,observed.st_size):raise RuntimeError('SDK_SOURCE_CHANGED')
  return os.fdopen(fd,'rb')
 except BaseException:
  os.close(fd);raise

def scan(site):
 root=Path(site);actual=[];total=0;entries=0
 if root.is_symlink() or not root.is_dir():raise RuntimeError('SDK_ROOT_INVALID')
 for p in root.rglob('*'):
  entries+=1
  if entries>30000:raise RuntimeError('SDK_ENTRY_COUNT_BOUND')
  st=p.lstat()
  if stat.S_ISLNK(st.st_mode):raise RuntimeError('SDK_SYMLINK')
  if stat.S_ISDIR(st.st_mode):continue
  if not stat.S_ISREG(st.st_mode) or st.st_size>MAX_FILE:raise RuntimeError('SDK_ENTRY_TYPE_OR_SIZE')
  total+=st.st_size
  if total>MAX_TOTAL or len(actual)>=MAX_FILES:raise RuntimeError('SDK_SIZE_BOUND')
  h=hashlib.sha256();count=0
  with open_regular(p,st) as f:
   while True:
    chunk=f.read(1048576)
    if not chunk:break
    count+=len(chunk)
    if count>st.st_size:raise RuntimeError('SDK_SOURCE_CHANGED')
    h.update(chunk)
  if count!=st.st_size:raise RuntimeError('SDK_SOURCE_CHANGED')
  actual.append({'path':str(p.relative_to(root)),'bytes':count,'sha256':h.hexdigest()})
 return sorted(actual,key=lambda row:row['path'])

def verify(site,manifest_path):
 if scan(site)!=expected_rows(manifest_path):raise RuntimeError('SDK_SNAPSHOT_CHANGED')

def build(manifest_path):
 expected=expected_rows(manifest_path)
 if scan(SOURCE)!=expected:raise RuntimeError('SDK_SOURCE_MISMATCH')
 if SNAPROOT.is_symlink() or not SNAPROOT.is_dir() or SNAPROOT.stat().st_uid!=os.geteuid() or SNAPROOT.stat().st_mode&0o077:raise RuntimeError('private owned snapshot root required')
 dest=Path(tempfile.mkdtemp(prefix='slug-bucket-sdk-',dir=str(SNAPROOT)))
 try:
  site=dest/'site';site.mkdir(mode=0o700)
  for row in expected:
   source=SOURCE/row['path'];target=site/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
   h=hashlib.sha256();count=0
   observed=source.lstat()
   if not stat.S_ISREG(observed.st_mode) or observed.st_size!=row['bytes']:raise RuntimeError('SDK_SOURCE_CHANGED')
   with open_regular(source,observed) as src,target.open('xb') as out:
    while True:
     chunk=src.read(1048576)
     if not chunk:break
     count+=len(chunk)
     if count>row['bytes']:raise RuntimeError('SDK_SOURCE_CHANGED')
     h.update(chunk);out.write(chunk)
    out.flush();os.fsync(out.fileno())
   if count!=row['bytes'] or h.hexdigest()!=row['sha256']:raise RuntimeError('SDK_SOURCE_CHANGED')
  if scan(SOURCE)!=expected or scan(site)!=expected:raise RuntimeError('SDK_SOURCE_OR_SNAPSHOT_CHANGED')
  for p in site.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o400)
  site.chmod(0o700)
  return dest,site
 except BaseException:
  try:shutil.rmtree(dest)
  except BaseException:raise SnapshotBuildError(dest) from None
  raise
