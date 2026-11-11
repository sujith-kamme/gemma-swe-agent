"""Review the patch before submitting.

Usage: check_diff.py

Shows changed files and the diff, and flags problems: edited test files (they
are discarded by the grader), stray scratch files, debug prints, breakpoints,
and an empty diff.
"""
import os
import re
import subprocess


def workspace():
    for c in [os.environ.get('SWE_WORKSPACE'), '/workspace', os.getcwd(), os.environ.get('HOME')]:
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


def git(ws, *a):
    return subprocess.run(['git', *a], cwd=ws, capture_output=True, text=True, timeout=30).stdout


def main():
    ws = workspace()
    status = [l for l in git(ws, 'status', '--porcelain', '--untracked-files=all').splitlines()
              if '.adk_exec_' not in l and '/tmp' not in l[3:] and not re.search(r'(^|/)tmp\w+/', l[3:])]
    if not status:
        print('EMPTY DIFF: nothing is changed. The task is not done.')
        return
    problems = []
    print('Changed files:')
    for l in status:
        path = l[3:].strip().strip('"')
        print(f'  {l[:2]} {path}')
        base = os.path.basename(path)
        if base.startswith('test_') or base.endswith('_test.py') or base == 'conftest.py' or '/tests/' in '/' + path:
            problems.append(f'{path}: test files are discarded by the grader. Revert it (git checkout -- {path}) unless it is your own scratch file, then delete it.')
        elif l.startswith('??') and re.search(r'(repro|debug|scratch|tmp|temp|check|reproduce|try)', base, re.I):
            problems.append(f'{path}: looks like a scratch file. Delete it (rm {path}).')
        elif l.startswith('??') and base.endswith(('.orig', '.rej', '.bak', '.log', '.txt', '.out')):
            problems.append(f'{path}: stray file. Delete it.')
    diff = git(ws, 'diff', 'HEAD')
    for line in diff.splitlines():
        if line.startswith('+') and not line.startswith('+++'):
            code = line[1:]
            if re.search(r'\bbreakpoint\(\)|\bpdb\.set_trace|\bimport pdb', code):
                problems.append(f'debugger left in: {code.strip()[:80]}')
            elif re.search(r'^\s*print\(\s*[f]?["\'](DEBUG|debug|>>>|XXX)', code):
                problems.append(f'debug print left in: {code.strip()[:80]}')
    print('\nDiff stat:\n' + git(ws, 'diff', 'HEAD', '--stat').rstrip())
    if len(diff) > 3500:
        print(diff[:3500] + f'\n... ({len(diff) - 3500} more chars)')
    else:
        print(diff)
    if problems:
        print('\nPROBLEMS:')
        for p in problems:
            print('  - ' + p)
    else:
        print('\nNo problems found.')


if __name__ == '__main__':
    main()
