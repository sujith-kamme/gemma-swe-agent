"""Write a throwaway pytest test, run it safely, and keep a copy for re-runs.

Usage:
  try_test.py --name <short_name> --code "<python test code with def test_...>" [--near tests/test_x.py]
  try_test.py --rerun <short_name>

The test is placed next to an existing test file (default: the main tests
directory) so the project's conftest fixtures apply, run with a 60 s timeout
and a memory cap, then deleted from the working tree. A copy is kept under
.git/swe_agent/ (never part of the patch) so `--rerun` can repeat it after the fix.
"""
import os
import resource
import signal
import subprocess
import sys


def workspace():
    for c in [os.environ.get('SWE_WORKSPACE'), '/workspace', os.getcwd(), os.environ.get('HOME')]:
        if not c or not os.path.isdir(c):
            continue
        try:
            top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=c, capture_output=True,
                                 text=True, timeout=10).stdout.strip()
        except Exception:
            top = ''
        if top:
            return top
    return os.getcwd()


def parse(argv):
    opts, key = {}, None
    for a in argv:
        if a == '--':
            continue
        if a.startswith('--') and key is None:
            key = a[2:]
        elif key is not None:
            opts[key] = a
            key = None
    return opts


def limit():
    os.setsid()
    try:
        resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    except Exception:
        pass


def run(cmd, cwd, timeout):
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=limit)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        return -9, (out or "") + f"\nTIMEOUT after {timeout}s: the code under test hangs (infinite loop or blocking call). That is likely the bug."


def main():
    o = parse(sys.argv[1:])
    ws = workspace()
    store = os.path.join(ws, '.git', 'swe_agent', 'tests')
    os.makedirs(store, exist_ok=True)
    name = (o.get('rerun') or o.get('name') or 'repro').replace('/', '_').replace('.py', '')
    saved = os.path.join(store, f'{name}.py')
    meta = saved + '.near'
    if 'rerun' in o:
        if not os.path.exists(saved):
            print(f'No saved test named {name}. Saved: {sorted(f[:-3] for f in os.listdir(store) if f.endswith(".py"))}')
            return
        code = open(saved).read()
        near = open(meta).read().strip() if os.path.exists(meta) else ''
    else:
        code = o.get('code', '')
        near = o.get('near', '')
        if 'def test' not in code:
            print('The code must define at least one `def test_...()` function using plain assert.')
            return
        open(saved, 'w').write(code)
        open(meta, 'w').write(near)
    if near and os.path.exists(os.path.join(ws, near)):
        tdir = os.path.dirname(os.path.join(ws, near))
    else:
        tdir = next((os.path.join(ws, d) for d in ('tests', 'test', 'testing') if os.path.isdir(os.path.join(ws, d))), ws)
    tmp = os.path.join(tdir, f'test_zz_swe_{name}.py')
    open(tmp, 'w').write(code)
    try:
        rc, out = run([sys.executable, '-m', 'pytest', tmp, '-q', '-p', 'no:cacheprovider', '--tb=short',
                       '-o', 'addopts=', '--no-header', '-rN'], ws, 30)
    finally:
        for f in (tmp, tmp + 'c'):
            if os.path.exists(f):
                os.remove(f)
        pyc = os.path.join(tdir, '__pycache__')
        if os.path.isdir(pyc):
            for f in os.listdir(pyc):
                if f.startswith(f'test_zz_swe_{name}.'):
                    os.remove(os.path.join(pyc, f))
    lines = out.strip().splitlines()
    if len(lines) > 45:
        lines = lines[:15] + ['...'] + lines[-28:]
    status = 'PASSED' if rc == 0 else ('TIMEOUT' if rc == -9 else 'FAILED')
    print(f'RESULT: {status}  (saved as "{name}"; rerun with --rerun {name})')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
