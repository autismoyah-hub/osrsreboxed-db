"""Restore bounded operator frames; retain raw HF logs separately as authority."""
import base64
import hashlib
import json
from pathlib import Path


def reconstruct_child_outputs(lines, output_dir):
    frames, expected, errors = {}, {}, []
    duplicate_frames = 0
    saw_frames = False
    for block in lines:
        for line in block.splitlines():
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                if '"child-output-frame"' in line:
                    errors.append('Malformed/truncated frame line')
                    saw_frames = True
                continue
            if not isinstance(row, dict):
                continue
            if row.get('event') == 'child-output-frame':
                saw_frames = True
                key = (row.get('stage'), row.get('stream'))
                try:
                    index = row['index']
                    if (row.get('version') != 1 or not isinstance(key[0], str)
                            or key[1] not in ('stdout', 'stderr')
                            or type(index) is not int or index < 0):
                        raise ValueError('Invalid frame identity')
                    data = base64.b64decode(row['base64'], validate=True)
                    if (len(data) != row['bytes'] or not 0 < len(data) <= 3072
                            or hashlib.sha256(data).hexdigest() != row['sha256']):
                        raise ValueError('Frame byte length/hash mismatch')
                    by_index = frames.setdefault(key, {})
                    if index in by_index:
                        if by_index[index] != data:
                            raise ValueError('Conflicting duplicate frame')
                        duplicate_frames += 1
                    else:
                        by_index[index] = data
                except (KeyError, ValueError, TypeError) as error:
                    errors.append(f'{key}: {error}')
            elif row.get('event') == 'stage-result' and 'outputTransport' in row:
                saw_frames = True
                for stream in ('stdout', 'stderr'):
                    key = (row.get('name'), stream)
                    metrics = row['outputTransport'].get(stream)
                    if key in expected and expected[key] != metrics:
                        errors.append(f'{key}: conflicting terminal stream metrics')
                    expected[key] = metrics
    if not saw_frames:
        return None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    streams = []
    for ordinal, key in enumerate(sorted(set(frames) | set(expected))):
        pieces = frames.get(key, {})
        metrics = expected.get(key)
        stream_errors = []
        if not isinstance(metrics, dict) or metrics.get('version') != 1:
            stream_errors.append('Terminal metrics unavailable')
        elif (type(metrics.get('frames')) is not int or metrics['frames'] < 0
              or len(pieces) != metrics['frames']
              or any(index != position for position, index in enumerate(sorted(pieces)))):
            stream_errors.append('Missing, extra, or non-contiguous frames')
        data = b''.join(pieces[i] for i in sorted(pieces))
        digest = hashlib.sha256(data).hexdigest()
        if isinstance(metrics, dict) and (len(data) != metrics.get('bytes') or digest != metrics.get('sha256')):
            stream_errors.append('Full stream byte length/hash mismatch')
        complete = not stream_errors and not errors
        file = f'{ordinal:03d}-{key[1]}' + ('.bin' if complete else '.partial.bin')
        with (output_dir / file).open('xb') as stream:
            stream.write(data)
        streams.append({'stage': key[0], 'stream': key[1], 'file': file,
                        'complete': complete, 'bytes': len(data), 'sha256': digest,
                        'frames': len(pieces), 'errors': stream_errors})
    report = {'version': 1, 'complete': bool(streams) and not errors and all(x['complete'] for x in streams),
              'duplicateIdenticalFrames': duplicate_frames, 'errors': errors, 'streams': streams,
              'scope': 'Per-stage stdout/stderr byte integrity only; not test, observation, or process-closure acceptance'}
    (output_dir / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
