# Measure v3 tools on every task (CPU): code localization (locate.py) and test-file finding
# (tests_for.py, run_tests.related). Competition tasks (design set) and mined tasks (held-out)
# are reported separately.
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import defaultdict
from pathlib import Path

T0 = time.time()
TOOLS = Path(glob.glob('/kaggle/input/**/gemma4-agent-v3/skills/tools/assets', recursive=True)[0])
COMP = Path(glob.glob('/kaggle/input/**/gemma-4-developer-agent/tasks.jsonl', recursive=True)[0]).parent
MINED = Path(glob.glob('/kaggle/input/**/mined/tasks.jsonl', recursive=True)[0]).parent
OUT = Path('/kaggle/working/measure')
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(TOOLS))
import run_tests  # noqa: E402  (for related())


def is_test(p):
    parts = p.split('/')
    n = parts[-1]
    return n.startswith('test_') or n.endswith('_test.py') or n == 'conftest.py' or any(x in ('tests', 'test', 'testing') for x in parts[:-1])


def files_of(patch):
    return re.findall(r'^\+\+\+ b/(\S+)', patch, re.M)


def run_tool(script, args, ws):
    r = subprocess.run([sys.executable, str(TOOLS / script), *args], cwd=ws, capture_output=True, text=True,
                       timeout=120, env={**os.environ, 'SWE_WORKSPACE': ws})
    return r.stdout


def measure(task, snap):
    gold_all = files_of(task['patch'])
    gold_src = [f for f in gold_all if f.endswith('.py') and not is_test(f)]
    test_files = [f for f in files_of(task['test_patch']) if f.endswith('.py') and not f.endswith('conftest.py')]
    row = dict(id=task['instance_id'], gold_src=gold_src, test_files=test_files,
               stmt_len=len(task['problem_statement']))
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(snap) as tf:
            tf.extractall(td)
        ws = td
        t = time.time()
        out = run_tool('locate.py', [task['problem_statement'][:4000]], ws)
        row['locate_s'] = round(time.time() - t, 1)
        top_files = re.findall(r'^  (\S+)  score=', out.split('Top files:')[1], re.M) if 'Top files:' in out else []
        sym_files = []
        for f in re.findall(r'^  (\S+?):\d+-\d+  ', out, re.M):
            if f not in sym_files:
                sym_files.append(f)
        g = set(gold_src)
        row['file_rank'] = next((i + 1 for i, f in enumerate(top_files) if f in g), None)
        row['sym_rank'] = next((i + 1 for i, f in enumerate(sym_files) if f in g), None)
        # test finding, given the true changed source file (oracle localization)
        tf_out = run_tool('tests_for.py', gold_src[:2], ws) if gold_src else ''
        tf_files = re.findall(r'^  (\S+)  score=', tf_out, re.M)
        tset = set(test_files)
        row['tests_for_rank'] = next((i + 1 for i, f in enumerate(tf_files) if f in tset), None)
        rel = run_tests.related(ws, gold_src) if gold_src else []
        row['run_tests_hit'] = bool(tset & set(rel))
        # realistic chain: tests_for on locate's top file
        if top_files:
            tf2 = re.findall(r'^  (\S+)  score=', run_tool('tests_for.py', top_files[:1], ws), re.M)
            row['chain_tests_rank'] = next((i + 1 for i, f in enumerate(tf2) if f in tset), None)
    return row


def summarize(rows):
    n = len(rows) or 1
    def rate(pred):
        return round(sum(1 for r in rows if pred(r)) / n, 3)
    return {
        'tasks': len(rows),
        'file_hit@1': rate(lambda r: r.get('file_rank') == 1),
        'file_hit@3': rate(lambda r: (r.get('file_rank') or 99) <= 3),
        'file_hit@5': rate(lambda r: (r.get('file_rank') or 99) <= 5),
        'symbol_file_hit@12': rate(lambda r: r.get('sym_rank') is not None),
        'tests_for_hit@1 (oracle src)': rate(lambda r: r.get('tests_for_rank') == 1),
        'tests_for_hit@3 (oracle src)': rate(lambda r: (r.get('tests_for_rank') or 99) <= 3),
        'run_tests_related_hit (oracle src)': rate(lambda r: r.get('run_tests_hit')),
        'chain_tests_hit@3 (locate top1 -> tests_for)': rate(lambda r: (r.get('chain_tests_rank') or 99) <= 3),
        'no_src_gold': sum(1 for r in rows if not r.get('gold_src')),
        'median_locate_s': sorted(r.get('locate_s', 0) for r in rows)[len(rows) // 2] if rows else 0,
    }


results = defaultdict(list)
for name, root in (('competition', COMP), ('mined', MINED)):
    tasks = [json.loads(l) for l in open(root / 'tasks.jsonl')]
    for i, t in enumerate(tasks, 1):
        snap = root / 'snapshots' / f"{t['instance_id']}.tgz"
        if not snap.exists():
            continue
        try:
            row = measure(t, snap)
        except Exception as e:
            row = {'id': t['instance_id'], 'error': f'{type(e).__name__}: {e}'}
        row['repo'] = t['repo']
        results[name].append(row)
        if i % 20 == 0:
            print(f'[{(time.time() - T0) / 60:5.1f}m] {name} {i}/{len(tasks)}', flush=True)
    (OUT / f'{name}_rows.json').write_text(json.dumps(results[name], indent=1))

summary = {name: summarize(rows) for name, rows in results.items()}
by_repo = {name: {repo: summarize([r for r in rows if r['repo'] == repo]) for repo in sorted({r['repo'] for r in rows})}
           for name, rows in results.items()}
(OUT / 'summary.json').write_text(json.dumps({'overall': summary, 'by_repo': by_repo}, indent=1))
print(json.dumps(summary, indent=1))
