"""Check the change before submitting, in one call: related existing tests, then a patch review.

Usage: check.py [test_file_or_node ...] [--query "<task title>"]

Runs run_tests.py (existing tests related to the modified files; each failure labeled
PRE-EXISTING or NEW) and then check_diff.py (changed files, diff, and PROBLEMS to fix).
"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if a != '--']
for script, extra, limit in (('run_tests.py', args, 100), ('check_diff.py', [], 15)):
    print(f'===== {script}', flush=True)
    try:
        r = subprocess.run([sys.executable, os.path.join(here, script), *extra], capture_output=True,
                           text=True, timeout=limit)
        print((r.stdout + r.stderr).strip()[-6000:])
    except subprocess.TimeoutExpired:
        print(f'{script} timed out after {limit}s')
