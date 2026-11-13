"""Check the change before submitting, in one call: a patch review, then related existing tests.

Usage: check.py [test_file_or_node ...] [--query "<task title>"]

Runs check_diff.py (PROBLEMS to fix, changed files, diff) and then run_tests.py (existing tests
related to the modified files; each failure labeled PRE-EXISTING or NEW). The test run gets only
the time the session has left, and is skipped when too little is left.
"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import locate  # noqa: E402

ws = locate.workspace()
args = [a for a in sys.argv[1:] if a != '--']


def run(script, extra, limit):
    try:
        r = subprocess.run([sys.executable, os.path.join(here, script), *extra], capture_output=True,
                           text=True, timeout=limit)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return f'{script} timed out after {limit}s'


review = run('check_diff.py', [], 15)
used = locate.elapsed(ws)
# Keep about a minute for one fix and submit_patch.
budget = 60 if used is None else min(60, locate.BUDGET_S - used - 60)
if budget < 15:
    tests = 'Tests skipped: too little time left. Call submit_patch now.'
else:
    tests = run('run_tests.py', [*args, '--timeout', str(budget)], 2 * budget + 20)
head = '\n'.join(l for l in (locate.clock(ws), '===== patch review', review) if l)
room = locate.OUT_CHARS - len(head) - 20
print(head + '\n===== tests\n' + (tests[-room:] if room > 200 else '(no room left: tests not shown)'))
