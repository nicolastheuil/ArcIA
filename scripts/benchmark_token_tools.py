"""Synthetic offline benchmark in Hermes. Prints metrics, never fixture content."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile


def run(argv, cwd):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, RTK_TELEMETRY_DISABLED='1'))


def main():
    result = {'synthetic_only': True, 'model_calls': 0}
    with tempfile.TemporaryDirectory(prefix='arcia-token-bench-') as directory:
        root = Path(directory)
        run(['git', 'init', '-q'], root)
        for index in range(120):
            (root/f'synthetic-{index:03}.txt').write_text('synthetic fixture\n')
        plain = run(['git', 'status', '--untracked-files=all'], root)
        reduced = run(['/opt/arcia-tools/bin/rtk', 'git', 'status'], root)
        result['rtk'] = {'plain_exit': plain.returncode, 'compressed_exit': reduced.returncode,
                         'plain_bytes': len(plain.stdout.encode()), 'compressed_bytes': len(reduced.stdout.encode()),
                         'reduced': bool(reduced.stdout) and len(reduced.stdout) < len(plain.stdout),
                         'status_context_retained': 'untracked' in reduced.stdout.casefold() or '120' in reduced.stdout,
                         'raw_output_recoverable': run(['git', 'status', '--untracked-files=all'], root).stdout == plain.stdout}
        run(['git','config','user.email','synthetic@example.test'],root)
        run(['git','config','user.name','Synthetic qualification'],root)
        run(['git','add','.'],root)
        run(['git','commit','-qm','Synthetic initial fixture'],root)
        for index in range(15):
            (root/'changes.txt').write_text('synthetic revision '+str(index))
            run(['git','add','changes.txt'],root)
            run(['git','commit','-qm','Synthetic controlled change '+str(index)+' with detailed explanatory text'],root)
        plain_log=run(['git','log','-15'],root)
        reduced_log=run(['/opt/arcia-tools/bin/rtk','git','log','-15'],root)
        result['rtk_log']={'plain_exit':plain_log.returncode,'compressed_exit':reduced_log.returncode,
            'plain_bytes':len(plain_log.stdout.encode()),'compressed_bytes':len(reduced_log.stdout.encode()),
            'reduced':bool(reduced_log.stdout) and len(reduced_log.stdout)<len(plain_log.stdout),
            'latest_change_retained':'Synthetic controlled change 14' in reduced_log.stdout}
    samples = [{'id': f'item-{i:03}', 'state': 'ok', 'detail': 'synthetic repeated service event'} for i in range(150)]
    samples[67] = {'id': 'item-067', 'state': 'FATAL', 'detail': 'SYNTHETIC_CRITICAL_MARKER_67'}
    messages = [{'role': 'user', 'content': 'Summarize synthetic events and identify failures.'},
                {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'synthetic-call', 'type': 'function', 'function': {'name': 'fixture', 'arguments': '{}'}}]},
                {'role': 'tool', 'tool_call_id': 'synthetic-call', 'content': json.dumps(samples)}]
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HEADROOM_UPDATE_CHECK='off')
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from headroom import compress
            compressed = compress(messages, model='gpt-4o')
        before = json.dumps(messages)
        after = json.dumps(compressed.messages)
        result['headroom'] = {'available': True, 'plain_bytes': len(before.encode()),
                              'compressed_bytes': len(after.encode()), 'reduced': len(after) < len(before),
                              'critical_marker_retained': 'SYNTHETIC_CRITICAL_MARKER_67' in after,
                              'hermes_wrapper_declared': False, 'production_quality_qualified': False}
    except Exception as exc:
        result['headroom'] = {'available': False, 'error_type': type(exc).__name__,
                              'hermes_wrapper_declared': False, 'production_quality_qualified': False}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
