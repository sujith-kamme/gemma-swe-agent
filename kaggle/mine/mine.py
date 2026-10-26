"""Kaggle CPU notebook: mine verified SWE tasks from public Python repos.

For each repo: clone, create an isolated environment with uv, install the
package with its test dependencies, mine and verify tasks (fail before fix,
pass after), and save the dependency wheels so offline GPU runs can install them.
Output (in /kaggle/working/mined): tasks.jsonl, snapshots/*.tgz, wheels/<repo>/, logs.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPOS = [
    # (github repo, extra pip packages for its tests)
    ('more-itertools/more-itertools', []),
    ('encode/starlette', ['httpx', 'anyio', 'trio', 'python-multipart', 'jinja2', 'itsdangerous', 'pyyaml']),
    ('fastapi/typer', ['shellingham', 'rich', 'coverage']),
    ('python-poetry/tomlkit', ['pyyaml']),
    ('arrow-py/arrow', ['python-dateutil', 'pytz', 'simplejson', 'dateparser', 'pytest-mock']),
    ('jd/tenacity', ['tornado', 'typeguard']),
    ('mahmoud/boltons', []),
    ('pytoolz/toolz', []),
    ('astanin/python-tabulate', ['wcwidth']),
    ('davidhalter/parso', []),
    ('PyCQA/pyflakes', []),
    ('andialbrecht/sqlparse', []),
    ('python-jsonschema/jsonschema', ['jsonschema-specifications', 'referencing', 'rpds-py']),
    ('PyCQA/isort', ['hypothesis', 'pytest-mock', 'black', 'colorama']),
    ('pygments/pygments', ['wcag-contrast-ratio']),
]
SINCE = '2022-01-01'
MAX_PER_REPO = 40
TIME_BUDGET_H = 11.0

OUT = Path('/kaggle/working/mined')
WORK = Path('/kaggle/tmp')
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)
T0 = time.time()
MINER = Path(__file__).with_name('mine_tasks.py') if '__file__' in globals() else None


def sh(cmd, **kw):
    print('$', cmd, flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print((r.stdout + r.stderr)[-1500:], flush=True)
    return r


sh(f'{sys.executable} -m pip install -q uv')
summary = {}
for repo, extras in REPOS:
    if (time.time() - T0) / 3600 > TIME_BUDGET_H:
        print('time budget reached')
        break
    name = repo.split('/')[-1].replace('-', '_').lower()
    src = WORK / 'repos' / name
    env = WORK / 'envs' / name
    if not src.exists():
        if sh(f'git clone -q https://github.com/{repo}.git {src}', timeout=1800).returncode:
            continue
    py = env / 'bin' / 'python'
    if not py.exists():
        sh(f'uv venv -q --python 3.12 {env}')
        base = f'uv pip install -q --python {py}'
        installed = False
        for spec in ('.[test]', '.[tests]', '.[testing]', '.[dev]', '.'):
            if sh(f'cd {src} && {base} -e "{spec}"', timeout=1800).returncode == 0:
                installed = True
                break
        if not installed:
            summary[repo] = 'install failed'
            continue
        for req in sorted(src.glob('requirements*/*test*.txt')) + sorted(src.glob('*requirements*test*.txt')) + sorted(src.glob('requirements/*.txt')):
            sh(f'cd {src} && {base} -r {req}', timeout=1800)
        sh(f'{base} pytest {" ".join(extras)}', timeout=1800)
    r = sh(f'{sys.executable} {MINER} --repo {repo} --repo-dir {src} --out {OUT} --since {SINCE} '
           f'--max {MAX_PER_REPO} --python {py}', timeout=int(3.5 * 3600))
    kept = [l for l in r.stdout.splitlines() if l.startswith('kept ')]
    summary[repo] = kept[-1] if kept else f'miner exit {r.returncode}'
    # wheels for offline use (everything installed except the repo itself)
    freeze = sh(f'uv pip freeze --python {py}').stdout
    reqs = [l for l in freeze.splitlines() if l and not l.startswith('-e') and ' @ ' not in l]
    (WORK / f'{name}_reqs.txt').write_text('\n'.join(reqs))
    sh(f'{sys.executable} -m pip download -q --only-binary=:all: --python-version 3.12 '
       f'-d {OUT}/wheels/{name} -r {WORK}/{name}_reqs.txt', timeout=1800)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(summary, flush=True)

n = sum(1 for _ in open(OUT / 'tasks.jsonl')) if (OUT / 'tasks.jsonl').exists() else 0
print(f'DONE: {n} tasks in {(time.time() - T0) / 3600:.1f} h', summary)
