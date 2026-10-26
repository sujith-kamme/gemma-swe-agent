# Gold-patch check for MINED tasks in the harness (Kaggle subprocess sandbox, CPU, offline).
# Confirms mined tasks load, run and pass with their reference fix, using only offline wheels.
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

T0 = time.time()


def log(msg):
    print(f'[{(time.time() - T0) / 60:6.1f}m] {msg}', flush=True)


# ---------------------------------------------------------------- 1. install wheelhouse
def find_input(*candidates):
    for c in candidates:
        hits = glob.glob(c)
        if hits:
            return Path(hits[0])
    raise FileNotFoundError(candidates)


WHEELHOUSE_DIR = find_input('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse',
                            '/kaggle/input/gemma-4-developer-agent-wheelhouse')
for pth in glob.glob('/usr/local/lib/python*/*-packages/*cutlass*.pth'):
    try:
        os.unlink(pth)
    except OSError:
        pass
tmp_whl = Path('/tmp/wheelhouse')
tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower():
        continue
    name = w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name
    if not (tmp_whl / name).exists():
        os.symlink(w, tmp_whl / name)
wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))
log(f'installing {len(wheels)} wheels')
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels],
               check=True)


# ---------------------------------------------------------------- 2. mined tasks' dependency wheels
MINED = Path(glob.glob('/kaggle/input/**/mined/tasks.jsonl', recursive=True)[0]).parent
harness_pkgs = {w.name.split('-')[0].lower().replace('_', '-') for w in WHEELHOUSE_DIR.glob('*.whl')}
extra = {}
for w in sorted(MINED.glob('wheels/*/*.whl')):
    pkg = w.name.split('-')[0].lower().replace('_', '-')
    if pkg not in harness_pkgs:
        extra[pkg] = str(w)          # one version per package (last repo wins)
log(f'installing {len(extra)} mined dependency wheels (skipping packages the harness ships)')
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *extra.values()])


import asyncio  # noqa: E402
from adk_submission import ModelRegistry  # noqa: E402
from adk_eval_core.tracing import SessionTrace  # noqa: E402
from swegemma.config import EvalConfig  # noqa: E402
from swegemma.evaluate import Evaluator  # noqa: E402
from swegemma.models import load_tasks  # noqa: E402


class GoldEvaluator(Evaluator):
    async def _run_agent_sandbox(self, task, *args, **kwargs):
        return task.patch, None, SessionTrace()


COMP = find_input('/kaggle/input/competitions/gemma-4-developer-agent', '/kaggle/input/gemma-4-developer-agent')
DATA = MINED
EMPTY = Path('/kaggle/working/empty'); EMPTY.mkdir(parents=True, exist_ok=True)
OUT = Path('/kaggle/working/gold')
OUT.mkdir(parents=True, exist_ok=True)
tasks = load_tasks(DATA / 'tasks.jsonl')
ev = GoldEvaluator(EvalConfig(
    tasks_path=DATA / 'tasks.jsonl', snapshots_dir=DATA / 'snapshots', results_dir=OUT / 'results',
    submission_dir=COMP / 'sample_submission', models=ModelRegistry(), sandbox='subprocess',
    verification_timeout_seconds=300, graph_dir=str(EMPTY),
    embeddings_dir=str(EMPTY), wheels_dir=DATA / 'wheels',
))
rows = []
for i, t in enumerate(tasks, 1):
    try:
        r = asyncio.run(ev.evaluate_task(task=t, task_index=i, total_tasks=len(tasks)))
        (OUT / f'{t.instance_id}.txt').write_text(r.test_output or '')
        tail = (r.test_output or '').strip().splitlines()[-2:]
        row = {'id': t.instance_id, 'resolved': bool(r.resolved), 'exit_code': r.test_exit_code, 'tail': tail}
    except Exception as e:
        row = {'id': t.instance_id, 'resolved': False, 'error': f'{type(e).__name__}: {e}'}
    rows.append(row)
    log(json.dumps(row)[:300])
    (OUT / 'gold_check.json').write_text(json.dumps(rows, indent=2))
log(f'DONE gold resolved {sum(r["resolved"] for r in rows)}/{len(rows)}')
