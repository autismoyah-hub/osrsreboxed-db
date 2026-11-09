"""Case candidate: copy reviewed private SDK to a fresh owned snapshot, verify full manifest."""
from pathlib import Path
import hashlib, json, shutil, tempfile
SOURCE=Path('/tmp/slug-hf-sdk/site-packages')
def build(manifest_path):
    expected=json.loads(Path(manifest_path).read_bytes())
    if not isinstance(expected,list) or not expected:
        raise RuntimeError('SDK_MANIFEST_INVALID')
    dest=Path(tempfile.mkdtemp(prefix='slug-bucket-sdk-',dir='/tmp'))
    try:
        shutil.copytree(SOURCE,dest/'site',symlinks=True)
        site=dest/'site'; actual=[]
        for p in sorted(site.rglob('*')):
            if p.is_symlink(): raise RuntimeError('SDK_SYMLINK')
            if p.is_file():
                b=p.read_bytes(); actual.append({'path':str(p.relative_to(site)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
            elif not p.is_dir(): raise RuntimeError('SDK_ENTRY_TYPE')
        if actual != expected: raise RuntimeError('SDK_MANIFEST_MISMATCH')
        for p in site.rglob('*'):
            p.chmod(0o700 if p.is_dir() else 0o400)
        site.chmod(0o700)
        return dest,site
    except BaseException:
        shutil.rmtree(dest,ignore_errors=True)
        raise

def verify(site, manifest_path):
    expected=json.loads(Path(manifest_path).read_bytes()); actual=[]
    for p in sorted(Path(site).rglob('*')):
        if p.is_symlink(): raise RuntimeError('SDK_SYMLINK')
        if p.is_file():
            b=p.read_bytes(); actual.append({'path':str(p.relative_to(site)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
        elif not p.is_dir(): raise RuntimeError('SDK_ENTRY_TYPE')
    if actual != expected: raise RuntimeError('SDK_SNAPSHOT_CHANGED')
