"""One bounded HF qualification job; default prints the request without submitting.

Run with the project-local .tools/hf-overflow/Scripts/python.exe.
--submit submits once; --collect retains status/logs without launching work.
An ambiguous submission is never automatically retried.
"""
import argparse
import dataclasses
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, default=str) + '\n')


def sync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / 'pilot.json')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--submit', action='store_true')
    action.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    here = plan_path.parent
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    payload = (here / plan.get('payloadFile', 'stage-bootstrap.py')).read_text(encoding='utf-8')
    receipt_path = here / 'submission.json'
    request = {key: plan[key] for key in ('name', 'image', 'flavor', 'timeout', 'attempts')}
    request.update(command=['/usr/local/bin/python3.9', '-c', payload], labels={
        'project': 'tsps', 'source': plan['source'], 'purpose': 'slug-export-qualification'})
    if not args.submit and not args.collect:
        print(json.dumps({'request': request, 'plan': plan}, indent=2))
        return

    if args.collect:
        raise RuntimeError('COLLECTION_INTEGRATION_HELD_NO_PROVIDER_CALL')

    from huggingface_hub import HfApi
    api = HfApi()
    identity = api.whoami()['name']  # Fails before submission if no account is connected.
    if args.submit:
        if plan.get('executionHold'):
            raise RuntimeError('Execution hold: ' + plan['executionHold'])
        package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
        if identity != package['namespace']:
            raise RuntimeError('Connected account differs from authorized package owner')
        if (request['flavor'] != package['flavor'] or request['attempts'] != 1
                or not 0 < request['timeout'] <= package['maximumJobSeconds']):
            raise RuntimeError('Request exceeds the frozen compute package')
        # None explicitly means no project-imposed concurrency ceiling.
        # Provider/account limits still apply at run_job; finite policies retain their guard.
        maximum = package['maximumConcurrentJobs']
        if maximum is not None:
            active = []
            terminal = {'COMPLETED', 'ERROR', 'CANCELED', 'CANCELLED', 'DELETED'}
            for job in api.list_jobs(namespace=identity, labels={'project': 'tsps'}):
                stage = getattr(job.status.stage, 'value', job.status.stage)
                if stage not in terminal:
                    active.append(job.id)
            if len(active) >= maximum:
                raise RuntimeError(f"{maximum} project cloud jobs already active; leave this request unsubmitted")
        # Exclusive intent prevents accidental duplicate submission after a timeout/restart.
        intent = {'stage': 'SUBMISSION_PENDING', 'utc': datetime.now(timezone.utc).isoformat(),
                  'namespace': identity, 'request': request,
                  'payloadSHA256': hashlib.sha256(payload.encode()).hexdigest(), 'plan': plan}
        with receipt_path.open('x', encoding='utf-8') as stream:
            json.dump(intent, stream, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        sync_dir(receipt_path.parent)
        info = api.run_job(namespace=identity, **request)
        intent.update(stage='SUBMITTED', job=dataclasses.asdict(info))
        tmp = receipt_path.with_name(receipt_path.name + '.submitted.tmp')
        with tmp.open('x', encoding='utf-8') as stream:
            json.dump(intent, stream, indent=2, default=str)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, receipt_path)
        sync_dir(receipt_path.parent)
        print(json.dumps({'stage': 'SUBMITTED', 'namespace': identity, 'jobId': info.id}))
        return



if __name__ == '__main__':
    main()
