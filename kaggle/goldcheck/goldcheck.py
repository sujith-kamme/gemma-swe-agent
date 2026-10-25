# Gold-patch solvability check for all tasks, Kaggle subprocess sandbox (CPU only, no model).
# A task whose gold patch fails here is unwinnable in this environment.
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


import asyncio  # noqa: E402
from adk_submission import ModelRegistry  # noqa: E402
from adk_eval_core.tracing import SessionTrace  # noqa: E402
from swegemma.config import EvalConfig  # noqa: E402
from swegemma.evaluate import Evaluator  # noqa: E402
from swegemma.models import load_tasks  # noqa: E402


class GoldEvaluator(Evaluator):
    async def _run_agent_sandbox(self, task, *args, **kwargs):
        return task.patch, None, SessionTrace()


DATA = find_input('/kaggle/input/competitions/gemma-4-developer-agent', '/kaggle/input/gemma-4-developer-agent')
OUT = Path('/kaggle/working/gold')
OUT.mkdir(parents=True, exist_ok=True)
tasks = load_tasks(DATA / 'tasks.jsonl')
ev = GoldEvaluator(EvalConfig(
    tasks_path=DATA / 'tasks.jsonl', snapshots_dir=DATA / 'snapshots', results_dir=OUT / 'results',
    submission_dir=DATA / 'sample_submission', models=ModelRegistry(), sandbox='subprocess',
    verification_timeout_seconds=300, graph_dir=str(DATA / 'graphs'),
    embeddings_dir=str(DATA / 'embeddings'), wheels_dir=DATA / 'wheels',
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
