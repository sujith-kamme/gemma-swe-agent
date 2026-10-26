"""Install the engineering tools into the repository's .git/swe/ folder (never part of the patch).

Run once, with no arguments. Afterwards call the tools with run_command, e.g.
  timeout 60 python .git/swe/locate.py "<title and key sentence>"
"""
import os
import shutil
import subprocess
import sys


def wrapper_cwd():
    # ADK's script wrapper chdirs into a temp dir (outside the repo on some sandboxes) and keeps
    # the original working directory, which is the repository, in a local variable `_orig_cwd`.
    f = sys._getframe()
    while f is not None:
        if '_orig_cwd' in f.f_locals:
            return f.f_locals['_orig_cwd']
        f = f.f_back
    return None


def workspace():
    for c in [os.environ.get('SWE_WORKSPACE'), wrapper_cwd(), '/workspace', os.getcwd(), os.environ.get('HOME')]:
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


here = os.path.dirname(os.path.abspath(globals().get('__file__', os.path.join(os.getcwd(), 'scripts', 'install.py'))))
assets = next(p for p in (os.path.join(here, '..', 'assets'), os.path.join(os.getcwd(), 'assets')) if os.path.isdir(p))
dest = os.path.join(workspace(), '.git', 'swe')
os.makedirs(dest, exist_ok=True)
names = sorted(f for f in os.listdir(assets) if f.endswith('.py'))
for f in names:
    shutil.copy(os.path.join(assets, f), os.path.join(dest, f))
print(f'Installed {", ".join(names)} into .git/swe/ (not part of the patch). Use them with run_command:')
print('''  timeout 60 python .git/swe/locate.py "<task title and key sentence>"     rank likely functions/files
  timeout 60 python .git/swe/tests_for.py <path/to/module.py> <Symbol> --query "<task title>"   related tests + style
  write_file(filepath=".git/swe/test_repro.py", content=<pytest test>)       then:
  timeout 60 python .git/swe/try_test.py .git/swe/test_repro.py --near <existing test file>
  timeout 120 python .git/swe/run_tests.py --query "<task title>" [test files]                     existing tests, failures labeled
  timeout 60 python .git/swe/check_diff.py                                   review patch before submit
  python .git/swe/notes.py add "<finding>"  |  python .git/swe/notes.py show''')
