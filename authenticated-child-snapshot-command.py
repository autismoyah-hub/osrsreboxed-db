"""Finite child-auth command delta, preserving caller prestart/intent guards.

The Python child executes the verified NONSECRET adapter source snapshot carried
in argv, never the subsequently mutable adapter path. Child alone retrieves its
authorized project secret. sdk_target is the reviewed private --target SDK root
if the actual child interpreter does not already have the SDK installed.
"""
from pathlib import Path
import base64
import hashlib

CHILD_BOOTSTRAP = """import base64,hashlib,sys,types
from pathlib import Path
snapshot=base64.b64decode(sys.argv.pop(1),validate=True)
digest=sys.argv.pop(1)
filename=sys.argv.pop(1)
sdk_target=sys.argv.pop(1)
if hashlib.sha256(snapshot).hexdigest()!=digest:raise SystemExit(1)
sys.argv[0]=filename
if sdk_target:sys.path.insert(0,sdk_target)
sys.path.insert(0,str(Path(filename).parent))
module=types.ModuleType('__main__')
module.__dict__.update(__file__=filename,__name__='__main__',__package__='',__spec__=None,__cached__=None)
sys.modules['__main__']=module
exec(compile(snapshot,filename,'exec'),module.__dict__)
"""


def authenticated_pilot_command(python, access_file, access_sha256,
                                pilot_file, pilot_sha256, plan_path, sdk_target=None):
    access_file, pilot_file = Path(access_file).resolve(), Path(pilot_file).resolve()
    adapter_snapshot = access_file.read_bytes()
    pilot_snapshot = pilot_file.read_bytes()
    if (hashlib.sha256(adapter_snapshot).hexdigest() != access_sha256
            or hashlib.sha256(pilot_snapshot).hexdigest() != pilot_sha256):
        raise RuntimeError('Reviewed child source identity mismatch')
    command = [str(python), '-c', CHILD_BOOTSTRAP,
               base64.b64encode(adapter_snapshot).decode('ascii'), access_sha256,
               str(access_file), str(Path(sdk_target).resolve()) if sdk_target else '',
               '--entry', str(pilot_file), '--entry-sha256', pilot_sha256,
               '--', '--plan', str(plan_path)]
    if any('\x00' in value or len(value.encode('utf-8')) + 1 >= 131072 for value in command):
        raise RuntimeError('Child control argv size/NUL bound exceeded')
    return command
