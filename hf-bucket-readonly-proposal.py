"""Supported project-secret access; never prints or persists secret material.

PROPOSAL: probe reads identity only; run mode permits only bucket read methods. Run mode executes an
independently reviewed, hash-pinned Python entry; it does not replace its guards.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import types
import shutil
import subprocess
import sys

PROJECT = '4cbb8d38-9dae-47c7-9736-c0020aea1c2a'
NAMESPACE = 'Autismo-Yah'
class AccessError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__()

METHODS = frozenset(('whoami', 'list_buckets'))


def obtain_secret():
    cli = shutil.which('cuttle') or shutil.which('cuttle.cmd')
    if not cli:
        raise AccessError('SUPPORTED_CUTTLE_CLI_MISSING')
    result = subprocess.run([cli, 'secrets', 'get', 'COMPUTE', '--project', PROJECT],
                            capture_output=True, text=True, timeout=45, check=False)
    # Never echo stdout/stderr: even a failing CLI could contain secret material.
    if result.returncode:
        raise AccessError('PROJECT_SECRET_ACCESS_FAILED')
    token = result.stdout.strip()
    if not token or '\n' in token or '\r' in token:
        raise AccessError('PROJECT_SECRET_INVALID_RESPONSE')
    return token


class ExplicitTokenApi:
    def __init__(self, original, token):
        self._api = original()
        self._token = token

    def __getattr__(self, name):
        if name not in METHODS:
            raise AccessError('UNREVIEWED_HF_METHOD')
        method = getattr(self._api, name)

        def call(*args, **kwargs):
            if 'token' in kwargs and kwargs['token'] != self._token:
                raise AccessError('AUTHORIZATION_SUBSTITUTION_REJECTED')
            kwargs['token'] = self._token  # Explicit on EVERY call, including generators.
            return method(*args, **kwargs)
        return call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--entry', type=Path)
    parser.add_argument('--entry-sha256')
    parser.add_argument('entry_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.probe == bool(args.entry):
        parser.error('Choose --probe OR --entry with --entry-sha256')
    if args.entry:
        if not args.entry_sha256 or len(args.entry_sha256) != 64:
            parser.error('Exact reviewed entry SHA256 required')
        entry = args.entry.resolve(strict=True)
        entry_snapshot = entry.read_bytes()
        if hashlib.sha256(entry_snapshot).hexdigest() != args.entry_sha256:
            raise AccessError('ENTRY_SHA256_MISMATCH')
        entry_code = compile(entry_snapshot, str(entry), 'exec')
    # Import before retrieving secret; missing dependency is a clean enablement error.
    import huggingface_hub
    original = huggingface_hub.HfApi
    token = obtain_secret()
    api = ExplicitTokenApi(original, token)
    identity = api.whoami()['name']
    if identity != NAMESPACE:
        raise AccessError('AUTHORIZED_NAMESPACE_MISMATCH')
    if args.probe:
        print(json.dumps(dict(stage='IDENTITY_ONLY_PASS', namespace=identity, secretPersisted=False)))
        return
    # Accepted callers import HfApi inside main. Bind all their calls explicitly.
    # No token in environment, argv, files, artifacts or another actor's context.
    huggingface_hub.HfApi = lambda *a, **kw: ExplicitTokenApi(original, token)
    sys.path.insert(0, str(entry.parent))
    sys.argv = [str(entry)] + (args.entry_args[1:] if args.entry_args[:1] == ['--'] else args.entry_args)
    previous_main = sys.modules.get('__main__')
    module = types.ModuleType('__main__')
    module.__dict__.update(__file__=str(entry), __name__='__main__',
                           __package__='', __spec__=None, __cached__=None)
    sys.modules['__main__'] = module
    try:
        exec(entry_code, module.__dict__)  # Execute ONLY the verified snapshot.
    finally:
        huggingface_hub.HfApi = original
        if previous_main is None:
            sys.modules.pop('__main__', None)
        else:
            sys.modules['__main__'] = previous_main


if __name__ == '__main__':
    try:
        main()
    except SystemExit as exc:
        # argparse/integer exits retain bounded status; string payloads never echo.
        if exc.code is None:
            sys.exit(0)
        if type(exc.code) is int and 0 <= exc.code <= 255:
            sys.exit(exc.code)
        print(json.dumps({'stage': 'ACCESS_OR_ENTRY_FAILED', 'error': 'SystemExit'}), file=sys.stderr)
        sys.exit(1)
    except BaseException as exc:
        # Do not serialize exception bodies/requests/headers from authenticated code.
        safe_codes = frozenset(('SUPPORTED_CUTTLE_CLI_MISSING', 'PROJECT_SECRET_ACCESS_FAILED',
            'PROJECT_SECRET_INVALID_RESPONSE', 'ENTRY_SHA256_MISMATCH',
            'AUTHORIZED_NAMESPACE_MISMATCH', 'UNREVIEWED_HF_METHOD',
            'AUTHORIZATION_SUBSTITUTION_REJECTED'))
        safe = exc.code if type(exc) is AccessError and exc.code in safe_codes else type(exc).__name__
        print(json.dumps({'stage': 'ACCESS_OR_ENTRY_FAILED', 'error': safe}), file=sys.stderr)
        sys.exit(1)
