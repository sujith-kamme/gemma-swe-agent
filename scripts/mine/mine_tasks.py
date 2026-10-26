"""Mine SWE tasks from a public Python repository's merged pull requests.

Mirrors the competition's curation pipeline:
  1. Commit/PR mining: first-parent commits whose message looks like a merged PR,
     that modify source .py files AND existing test files (no new test files).
  2. Problem statement = PR title + description (commit subject + body).
  3. Filters: small source change, no docs-only / mechanical changes.
  4. Execution verification: test files fail with only the test patch applied
     (fail-to-pass) and pass with the source patch too (pass-to-pass).

Usage:
  python mine_tasks.py --repo pallets/click --out OUT_DIR [--since 2023-01-01] [--max 40] [--python python3]
The repository's test dependencies must already be installed for --python
(see repos.json in this folder). Writes OUT_DIR/tasks.jsonl and OUT_DIR/snapshots/<id>.tgz.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

TRAILER = re.compile(r'^(Co-authored-by|Signed-off-by|Reviewed-by|Change-Id):.*$', re.I | re.M)
SKIP_TITLE = re.compile(r'\b(bump|release|version|changelog|typo|lint|format|pre-commit|ci|deps?|dependabot|revert|merge branch)\b', re.I)


def sh(cmd, cwd=None, timeout=600, check=False):
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f'{cmd}: {r.stderr[-500:]}')
    return r


def is_test(path):
    parts = path.split('/')
    name = parts[-1]
    return (name.startswith('test_') or name.endswith('_test.py') or name == 'conftest.py'
            or any(p in ('tests', 'test', 'testing') for p in parts[:-1]))


def is_doc(path):
    return path.startswith(('docs/', 'doc/', '.github/')) or path.endswith(('.md', '.rst', '.txt', '.cfg', '.toml', '.yml', '.yaml', '.ini'))


def candidates(repo_dir, since, max_src_files=3, max_src_lines=200):
    log = sh(['git', 'log', '--first-parent', f'--since={since}', '--format=%H%x00%P%x00%s%x00%b%x1e'], cwd=repo_dir, check=True).stdout
    for rec in log.split('\x1e'):
        rec = rec.strip('\n')
        if not rec:
            continue
        sha, parents, subject, body = (rec.split('\x00') + ['', '', '', ''])[:4]
        parents = parents.split()
        if not parents:
            continue
        parent = parents[0]
        pr = re.search(r'\(#(\d+)\)\s*$', subject) or re.search(r'Merge pull request #(\d+)', subject)
        if not pr or SKIP_TITLE.search(subject):
            continue
        if subject.startswith('Merge pull request'):
            # merge commit: the PR title is the first body line
            lines = body.strip().splitlines()
            subject, body = (lines[0], '\n'.join(lines[1:])) if lines else (subject, '')
        status = sh(['git', 'diff', '--name-status', parent, sha], cwd=repo_dir).stdout.split('\n')
        files = [l.split('\t') for l in status if l.strip()]
        tests = [f[-1] for f in files if is_test(f[-1]) and f[-1].endswith('.py')]
        new_tests = [f[-1] for f in files if f[0].startswith('A') and is_test(f[-1])]
        src = [f[-1] for f in files if f[-1].endswith('.py') and not is_test(f[-1]) and not is_doc(f[-1])]
        if not tests or new_tests or not src or len(src) > max_src_files:
            continue
        if any(s.startswith('src/') for s in src):
            continue  # the Kaggle subprocess sandbox cannot install src-layout packages
        nonsrc = [f[-1] for f in files if not is_test(f[-1])]
        stat = sh(['git', 'diff', '--numstat', parent, sha, '--', *src], cwd=repo_dir).stdout
        lines = sum(int(a) + int(b) for a, b, _ in (l.split('\t') for l in stat.splitlines() if l and l[0].isdigit()))
        if lines > max_src_lines:
            continue
        patch = sh(['git', 'diff', parent, sha, '--', *nonsrc], cwd=repo_dir).stdout
        test_patch = sh(['git', 'diff', parent, sha, '--', *[f[-1] for f in files if is_test(f[-1])]], cwd=repo_dir).stdout
        statement = (re.sub(r'\s*\(#\d+\)\s*$', '', subject) + '\n\n' + TRAILER.sub('', body).strip()).strip()
        date = sh(['git', 'show', '-s', '--format=%cI', sha], cwd=repo_dir).stdout.strip()
        yield dict(pr=pr.group(1), sha=sha, base_commit=parent, patch=patch, test_patch=test_patch,
                   problem_statement=statement, created_at=date, test_files=sorted(set(tests)))


def run_tests(work, python, test_files, timeout=300):
    r = sh([python, '-m', 'pytest', *test_files, '-q', '-p', 'no:cacheprovider', '-x', '--no-header', '-o', 'addopts='],
           cwd=work, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def apply(work, patch):
    if not patch.strip():
        return True
    p = os.path.join(work, '.swe_patch.diff')
    open(p, 'w').write(patch)
    ok = sh(['git', 'apply', '--whitespace=nowarn', p], cwd=work).returncode == 0
    os.remove(p)
    return ok


def verify(repo_dir, cand, python, src_on_path):
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, 'w')
        sh(['git', 'worktree', 'add', '--detach', work, cand['base_commit']], cwd=repo_dir, check=True)
        try:
            env_path = os.environ.copy()
            if not apply(work, cand['test_patch']):
                return False, 'test_patch does not apply'
            os.environ['PYTHONPATH'] = os.path.join(work, 'src') if src_on_path else work
            rc1, out1 = run_tests(work, python, cand['test_files'])
            if rc1 == 0:
                return False, 'tests pass before the fix'
            if 'ModuleNotFoundError' in out1 or 'ImportError while importing' in out1 and 'cannot import name' not in out1:
                return False, 'environment import error before fix'
            if not apply(work, cand['patch']):
                return False, 'patch does not apply'
            rc2, out2 = run_tests(work, python, cand['test_files'])
            if rc2 != 0:
                return False, 'tests fail after the fix: ' + out2[-200:]
            return True, 'ok'
        finally:
            os.environ.clear()
            os.environ.update(env_path)
            sh(['git', 'worktree', 'remove', '--force', work], cwd=repo_dir)


def snapshot(repo_dir, base_commit, dest):
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, 'snap')
        sh(['git', 'worktree', 'add', '--detach', work, base_commit], cwd=repo_dir, check=True)
        try:
            shutil.rmtree(os.path.join(work, '.git'), ignore_errors=True)
            if os.path.isfile(os.path.join(work, '.git')):
                os.remove(os.path.join(work, '.git'))
            sh('git init -q && git add -A && git -c user.email=m@m -c user.name=miner commit -q -m base', cwd=work, check=True)
            with tarfile.open(dest, 'w:gz') as tf:
                tf.add(work, arcname='.')
        finally:
            sh(['git', 'worktree', 'remove', '--force', work], cwd=repo_dir)
            sh(['git', 'worktree', 'prune'], cwd=repo_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True)          # org/name on GitHub
    ap.add_argument('--repo-dir', default=None)        # existing clone (default: clone into OUT/repos)
    ap.add_argument('--out', required=True)
    ap.add_argument('--since', default='2023-01-01')
    ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--python', default='python3')
    ap.add_argument('--src-layout', action='store_true')
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'snapshots'), exist_ok=True)
    name = a.repo.split('/')[-1].replace('-', '_').lower()
    repo_dir = a.repo_dir or os.path.join(a.out, 'repos', name)
    if not os.path.isdir(repo_dir):
        sh(['git', 'clone', '-q', f'https://github.com/{a.repo}.git', repo_dir], check=True, timeout=1800)
    done = set()
    tasks_path = os.path.join(a.out, 'tasks.jsonl')
    if os.path.exists(tasks_path):
        done = {json.loads(l)['instance_id'] for l in open(tasks_path)}
    log = open(os.path.join(a.out, f'mine_{name}.log'), 'a')
    kept = 0
    for cand in candidates(repo_dir, a.since):
        iid = f"{name}_{cand['pr']}"
        if iid in done:
            continue
        try:
            ok, why = verify(repo_dir, cand, a.python, a.src_layout)
        except Exception as e:
            ok, why = False, f'error: {e}'
        log.write(f'{iid}\t{ok}\t{why}\n')
        log.flush()
        print(f'{iid}: {why}', flush=True)
        if not ok:
            continue
        snapshot(repo_dir, cand['base_commit'], os.path.join(a.out, 'snapshots', f'{iid}.tgz'))
        rec = dict(instance_id=iid, repo=a.repo, base_commit=cand['base_commit'], patch=cand['patch'],
                   test_patch=cand['test_patch'], problem_statement=cand['problem_statement'],
                   hints_text='', created_at=cand['created_at'])
        with open(tasks_path, 'a') as f:
            f.write(json.dumps(rec) + '\n')
        kept += 1
        if kept >= a.max:
            break
    print(f'kept {kept} tasks for {a.repo}')


if __name__ == '__main__':
    main()
