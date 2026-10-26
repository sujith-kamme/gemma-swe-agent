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


def new_test_files(tp):
    out, cur, first = set(), None, False
    for l in tp.splitlines():
        m = re.match(r'^\+\+\+ b/(\S+)', l)
        if m:
            cur, first = m.group(1), True
            continue
        if cur and l.startswith('@@'):
            if first and l.startswith('@@ -0,0 '):
                out.add(cur)
            first = False
    return out


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
        tset = set(test_files) - new_test_files(task['test_patch'])   # only files that exist at base
        row['existing_test_files'] = sorted(tset)
        q = task['problem_statement'].split('\n\n')[0][:300]
        def tf_rank(args):
            files = re.findall(r'^  (\S+)  score=', run_tool('tests_for.py', args, ws), re.M)
            return next((i + 1 for i, f in enumerate(files) if f in tset), None)
        row['tests_for_rank'] = tf_rank(gold_src[:2]) if gold_src else None
        row['tests_for_q_rank'] = tf_rank(gold_src[:2] + ['--query', q]) if gold_src else None
        row['query_only_rank'] = tf_rank(['--query', q])
        rel = run_tests.related(ws, gold_src, task['problem_statement'].split('\n\n')[0][:300]) if gold_src else []
        row['run_tests_hit'] = bool(tset & set(rel))
        # realistic chain: tests_for on locate's top file
        if top_files:
            row['chain_tests_rank'] = tf_rank(top_files[:1])
            row['chain_q_rank'] = tf_rank(top_files[:1] + ['--query', q])
    return row


def summarize(rows):
    n = len(rows) or 1
    def rate(pred):
        return round(sum(1 for r in rows if pred(r)) / n, 3)
    ex = [r for r in rows if r.get('existing_test_files')]
    m = len(ex) or 1
    def trate(key, k=3):
        return round(sum(1 for r in ex if (r.get(key) or 99) <= k) / m, 3)
    tests = {'tasks_with_existing_test_file': len(ex),
             'tests@1 module only': trate('tests_for_rank', 1), 'tests@3 module only': trate('tests_for_rank'),
             'tests@1 module+query': trate('tests_for_q_rank', 1), 'tests@3 module+query': trate('tests_for_q_rank'),
             'tests@3 query only': trate('query_only_rank'),
             'chain@3 locate top1': trate('chain_tests_rank'), 'chain@3 locate top1+query': trate('chain_q_rank')}
    return {**tests,
        'tasks': len(rows),
        'file_hit@1': rate(lambda r: r.get('file_rank') == 1),
        'file_hit@3': rate(lambda r: (r.get('file_rank') or 99) <= 3),
        'file_hit@5': rate(lambda r: (r.get('file_rank') or 99) <= 5),
        'symbol_file_hit@12': rate(lambda r: r.get('sym_rank') is not None),
        'run_tests_related_hit (oracle src, existing)': round(sum(1 for r in ex if r.get('run_tests_hit')) / m, 3),
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
