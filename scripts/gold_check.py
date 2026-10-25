"""Verify tasks with the GOLD patch as the "agent" patch (no model needed).

Tells us which tasks are solvable in a given sandbox backend. A gold patch that
fails verification means the environment, not the agent, is at fault.

Usage:
  python scripts/gold_check.py --data <dataset_dir> --sandbox docker|subprocess \
      --out <results_dir> [task_id ...]
"""
import argparse
import asyncio
import json
from pathlib import Path

from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.evaluate import Evaluator
from swegemma.models import load_tasks
from adk_eval_core.tracing import SessionTrace


class GoldEvaluator(Evaluator):
    async def _run_agent_sandbox(self, task, *args, **kwargs):
        return task.patch, None, SessionTrace()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--sandbox', default='docker')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('ids', nargs='*')
    a = ap.parse_args()

    tasks = [t for t in load_tasks(a.data / 'tasks.jsonl') if not a.ids or t.instance_id in a.ids]
    ev = GoldEvaluator(EvalConfig(
        tasks_path=a.data / 'tasks.jsonl', snapshots_dir=a.data / 'snapshots', results_dir=a.out,
        submission_dir=a.data / 'sample_submission', models=ModelRegistry(), sandbox=a.sandbox,
        verification_timeout_seconds=300, graph_dir=str(a.data / 'graphs'),
        embeddings_dir=str(a.data / 'embeddings'), wheels_dir=a.data / 'wheels',
    ))
    rows = []
    for i, t in enumerate(tasks, 1):
        r = asyncio.run(ev.evaluate_task(task=t, task_index=i, total_tasks=len(tasks)))
        tail = (r.test_output or '').strip().splitlines()[-3:]
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / f'{t.instance_id}.txt').write_text(r.test_output or '')
        rows.append({'id': t.instance_id, 'resolved': bool(r.resolved), 'exit_code': r.test_exit_code,
                     'tail': tail})
        print(json.dumps(rows[-1]), flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'gold_check.json').write_text(json.dumps(rows, indent=2))
    print(f'gold resolved {sum(r["resolved"] for r in rows)}/{len(rows)}')


if __name__ == '__main__':
    main()
