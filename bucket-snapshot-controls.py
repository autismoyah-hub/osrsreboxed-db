"""UNRUN fake-only SDK snapshot controls; no SDK, secret, network or provider."""
import hashlib,importlib.util,json,os,pathlib,shutil,tempfile
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('bucket_snapshot',HERE/'bucket-sdk-snapshot.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='slug-bucket-snapshot-controls-') as tmp:
 root=pathlib.Path(tmp);src=root/'source';src.mkdir();m.SOURCE=src;m.SNAPROOT=root/'snapshots';m.SNAPROOT.mkdir(mode=0o700)
 (src/'one.txt').write_bytes(b'synthetic');(src/'nested').mkdir();(src/'nested/two.txt').write_bytes(b'only')
 def row(name):
  b=(src/name).read_bytes();return {'path':name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
 manifest=root/'manifest.json';rows=[row('nested/two.txt'),row('one.txt')];manifest.write_text(json.dumps(rows))
 assert m.expected_rows(manifest)==rows
 unsorted=root/'unsorted.json';unsorted.write_text(json.dumps(list(reversed(rows))))
 try:m.expected_rows(unsorted)
 except RuntimeError as exc:assert str(exc)=='SDK_MANIFEST_ORDER'
 else:raise AssertionError('unsorted manifest accepted')
 dest,site=m.build(manifest)
 try:m.verify(site,manifest)
 finally:shutil.rmtree(dest)
 original=m.MAX_FILE;m.MAX_FILE=3
 try:
  try:m.build(manifest)
  except RuntimeError:pass
  else:raise AssertionError('oversize accepted')
 finally:m.MAX_FILE=original
 (src/'link').symlink_to(src/'one.txt')
 try:
  try:m.build(manifest)
  except RuntimeError:pass
  else:raise AssertionError('symlink accepted')
 finally:(src/'link').unlink()
 original_stat=(src/'one.txt').lstat();(src/'one.txt').rename(src/'saved.txt');os.mkfifo(src/'one.txt')
 try:
  try:m.open_regular(src/'one.txt',original_stat)
  except RuntimeError:pass
  else:raise AssertionError('FIFO replacement accepted')
 finally:(src/'one.txt').unlink();(src/'saved.txt').rename(src/'one.txt')
 (src/'one.txt').write_bytes(b'changed')
 try:
  try:m.build(manifest)
  except RuntimeError:pass
  else:raise AssertionError('source mismatch accepted')
 finally:(src/'one.txt').write_bytes(b'synthetic')
 old_scan=m.scan;old_remove=m.shutil.rmtree;calls=[0];retained=None
 def fail_site(path):
  calls[0]+=1
  if calls[0]==3:raise RuntimeError('synthetic snapshot verification failure')
  return old_scan(path)
 def fail_cleanup(path,*args,**kwargs):raise OSError('synthetic cleanup failure')
 m.scan=fail_site;m.shutil.rmtree=fail_cleanup
 try:
  try:m.build(manifest)
  except m.SnapshotBuildError as exc:retained=pathlib.Path(exc.snapshotPath);assert retained.exists()
  else:raise AssertionError('cleanup failure swallowed')
 finally:
  m.scan=old_scan;m.shutil.rmtree=old_remove
  if retained is not None:old_remove(retained)
print('PASS: synthetic snapshot order, match, size, symlink, FIFO race, mutation and retained cleanup failure')
