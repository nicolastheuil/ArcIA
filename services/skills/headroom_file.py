"""Local structured-file compression, before the file is sent to a model."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile

WORKSPACE = Path('/opt/data/workspace')
MAX_BYTES = 512*1024


def read_source(value, workspace=WORKSPACE):
    root = workspace.resolve()
    path = Path(value)
    path = path if path.is_absolute() else root/path
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('HEADROOM_WORKSPACE_SCOPE')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('HEADROOM_FILE_TOO_LARGE')
    parsed = json.loads(raw)
    if not isinstance(parsed, (list, dict)):
        raise ValueError('HEADROOM_JSON_REQUIRED')
    return path.resolve(), raw


def compress_text(content):
    if len(content.encode()) < 4096:return content
    with tempfile.TemporaryDirectory(prefix='arcia-headroom-') as temporary:
        os.environ.update(HOME=temporary, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                          HEADROOM_UPDATE_CHECK='off', DISABLE_TELEMETRY='1')
        messages = [{'role': 'user', 'content': 'Analyze these structured results; preserve failures.'},
                    {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'local-file', 'type': 'function', 'function': {'name': 'read_json', 'arguments': '{}'}}]},
                    {'role': 'tool', 'tool_call_id': 'local-file', 'content': content}]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from headroom import compress
            result = compress(messages, model='gpt-4o')
        return next((m['content'] for m in result.messages if m.get('role') == 'tool' and isinstance(m.get('content'), str)), content)


def main():
    try:
        stdin_mode=len(sys.argv)>1 and sys.argv[1]=='--stdin'
        if stdin_mode:
            raw=sys.stdin.buffer.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError('HEADROOM_INPUT_TOO_LARGE')
            json.loads(raw);path=None
        else:path,raw=read_source(sys.argv[1])
        content=raw.decode('utf-8');reduced=compress_text(content)
        if len(reduced.encode()) >= len(raw):
            reduced = content
        print(json.dumps({'success': True, 'content': reduced, 'original_file': str(path) if path else None,
                          'original_sha256': hashlib.sha256(raw).hexdigest(), 'original_bytes': len(raw),
                          'result_bytes': len(reduced.encode()), 'compressed': reduced != content,
                          'notice': 'Lossy overview. Read the original file for exact counts, quotations or omitted details. No shared memory or provider call.'}))
    except Exception:
        print(json.dumps({'success': False, 'code': 'HEADROOM_FILE_REFUSED'}))


if __name__ == '__main__':
    main()
