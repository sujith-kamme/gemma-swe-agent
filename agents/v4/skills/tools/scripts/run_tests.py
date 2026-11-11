"""Run the existing tests related to your change and classify every failure.

Usage: run_tests.py [test_file_or_node ...] [--query "<task title>"]

With no test files given, picks test files related to the modified source files
(git diff) and to the task title (same ranking as tests_for.py). Runs them with a timeout. For each failing test it re-runs that
test on the original code (your changes stashed, then restored) and reports:
  PRE-EXISTING  fails without your change too: not caused by you
  NEW           passes without your change: a regression, or the behavior change the task asks for
"""
import os
import re
import resource
import signal
import subprocess
import sys

SKIP_DIRS = {'.git', '.tox', '.venv', 'venv', 'env', 'node_modules', 'build', 'dist', '__pycache__', 'site-packages'}


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


def git(ws, *a):
    return subprocess.run(['git', *a], cwd=ws, capture_output=True, text=True, timeout=30)


def limit():
    os.setsid()
    try:
        resource.setrlimit(resource.RLIMIT_AS, (6 << 30, 6 << 30))
    except Exception:
        pass


def pytest(ws, targets, timeout):
    cmd = [sys.executable, '-m', 'pytest', *targets, '-q', '-rfE', '--tb=line', '-p', 'no:cacheprovider', '--no-header',
           '--continue-on-collection-errors']
    p = subprocess.Popen(cmd, cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=limit)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out, False
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        return -9, out or '', True


def is_test(rel):
    n = os.path.basename(rel)
    return n.startswith('test_') or n.endswith('_test.py') or '/tests/' in '/' + rel or n == 'conftest.py'


def related(ws, changed, query=''):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import tests_for
        _, _, scores, _ = tests_for.rank(ws, changed, query)
        if scores:
            return [r for r, _ in scores.most_common(3)]
    except Exception:
        pass
    return related_by_imports(ws, changed)


def related_by_imports(ws, changed):
    stems = {os.path.basename(c)[:-3].lstrip('_') for c in changed if c.endswith('.py')}
    mods = set()
    for c in changed:
        if c.endswith('.py'):
            parts = c[:-3].split('/')
            if parts[0] == 'src':
                parts = parts[1:]
            if parts[-1] == '__init__':
                parts = parts[:-1]
            if parts:
                mods.add('.'.join(parts))
    found = {}
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), ws)
            if not f.endswith('.py') or not is_test(rel) or f == 'conftest.py' or f.startswith('test_zz_swe_'):
                continue
            score = 10 if any(s and s in f for s in stems) else 0
            try:
                txt = open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
                score += sum(3 for m in mods if re.search(r'(from|import)\s+' + re.escape(m) + r'\b', txt))
            except Exception:
                pass
            if score:
                found[rel] = score
    return [r for r, _ in sorted(found.items(), key=lambda x: -x[1])[:3]]


def main():
    ws = workspace()
    targets = [a for a in sys.argv[1:] if a != '--']
    query = ''
    if '--query' in targets:
        i = targets.index('--query')
        query = ' '.join(targets[i + 1:i + 2])
        del targets[i:i + 2]
    changed = [l[3:].strip() for l in git(ws, 'status', '--porcelain').stdout.splitlines() if l[3:].strip().endswith('.py')]
    if not targets:
        targets = related(ws, [c for c in changed if not is_test(c)], query)
        if not targets:
            print('No related test files found. Pass test files explicitly, e.g. run_tests.py tests/test_x.py')
            return
    print('Running: ' + ' '.join(targets))
    rc, out, to = pytest(ws, targets, 55)
    summary = [l for l in out.splitlines() if re.search(r'\d+ (passed|failed|error)', l)]
    print('Summary: ' + (summary[-1].strip() if summary else ('TIMEOUT after 55s' if to else out.strip()[-300:])))
    broken = sorted(set(re.findall(r'^ERROR (\S+\.py)\s*$', out, re.M)) | set(re.findall(r'^ERROR (\S+\.py) - ', out, re.M)))
    for b in broken:
        miss = re.search(r'No module named [\'"]?([\w.]+)', out)
        print(f'  COLLECTION ERROR {b}: cannot import ({"missing module " + miss.group(1) if miss else "see output"}). Not caused by a small edit unless you broke an import.')
    failed = sorted(set(re.findall(r'^(?:FAILED|ERROR) (\S+::\S+)', out, re.M)))
    if rc == 0 or not failed:
        if rc != 0 and not broken:
            print(out.strip()[-1500:])
        return
    reasons = {}
    for l in out.splitlines():
        m = re.match(r'^(?:FAILED|ERROR) (\S+::\S+?)(?: - (.*))?$', l)
        if m:
            reasons[m.group(1)] = (m.group(2) or '')[:160]
    pre = set()
    if changed and len(failed) <= 30:
        st = git(ws, 'stash', 'push', '-q')
        if st.returncode == 0:
            try:
                _, out0, _ = pytest(ws, failed, 40)
                passed_before = set(failed) - set(re.findall(r'^(?:FAILED|ERROR) (\S+::\S+)', out0, re.M))
                if re.search(r'\d+ (passed|failed)', out0):
                    pre = set(failed) - passed_before
            finally:
                pop = git(ws, 'stash', 'pop', '-q')
                if pop.returncode != 0:
                    print('WARNING: could not restore your changes automatically. Run: git stash pop')
    for f in failed:
        tag = 'PRE-EXISTING' if f in pre else 'NEW'
        print(f'  {tag:12} {f}  {reasons.get(f, "")}')
    if any(f not in pre for f in failed):
        print('NEW failures: fix them unless the task explicitly changes that behavior (then the hidden tests expect the new behavior).')


if __name__ == '__main__':
    main()
