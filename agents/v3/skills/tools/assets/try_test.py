"""Run a throwaway pytest test file safely, next to the project's tests.

Usage: python .git/swe/try_test.py <test file> [--near <existing test file>]

Write the test first with write_file, e.g. to .git/swe/test_repro.py (never part of
the patch). This copies it next to an existing test file (default: the main tests
directory) so the project's conftest fixtures apply, runs it with a 30 s timeout
and a memory cap, then deletes the copy. Re-run the same command after the fix.
"""
import os
import resource
import shutil
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
        return -9, (out or '') + f'\nTIMEOUT after {timeout}s: the code under test hangs (infinite loop or blocking call).'


def main():
    args = [a for a in sys.argv[1:] if a != '--']
    near = ''
    if '--near' in args:
        i = args.index('--near')
        near = args[i + 1] if i + 1 < len(args) else ''
        del args[i:i + 2]
    if not args:
        print('usage: python .git/swe/try_test.py <test file> [--near <existing test file>]')
        return
    ws = workspace()
    src = args[0] if os.path.isabs(args[0]) else os.path.join(ws, args[0])
    if not os.path.exists(src):
        print(f'{args[0]} does not exist. Write it first with write_file(filepath=".git/swe/test_repro.py", content=...).')
        return
    if 'def test' not in open(src, encoding='utf-8', errors='replace').read():
        print('The file must define at least one `def test_...()` function using plain assert.')
        return
    if near and os.path.exists(os.path.join(ws, near)):
        tdir = os.path.dirname(os.path.join(ws, near))
    else:
        tdir = next((os.path.join(ws, d) for d in ('tests', 'test', 'testing') if os.path.isdir(os.path.join(ws, d))), ws)
    base = os.path.splitext(os.path.basename(src))[0]
    tmp = os.path.join(tdir, f'test_zz_swe_{base}.py')
    shutil.copy(src, tmp)
    try:
        rc, out = run([sys.executable, '-m', 'pytest', tmp, '-q', '-p', 'no:cacheprovider', '--tb=short',
                       '-o', 'addopts=', '--no-header', '-rN'], ws, 30)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
        pyc = os.path.join(tdir, '__pycache__')
        if os.path.isdir(pyc):
            for f in os.listdir(pyc):
                if f.startswith(f'test_zz_swe_{base}.'):
                    os.remove(os.path.join(pyc, f))
    lines = out.strip().replace(tmp, args[0]).splitlines()
    if len(lines) > 45:
        lines = lines[:15] + ['...'] + lines[-28:]
    status = 'PASSED' if rc == 0 else ('TIMEOUT' if rc == -9 else 'FAILED')
    print(f'RESULT: {status}')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
