"""A small notebook that survives context summaries.

Usage:
  notes.py add "<one-line finding>"   e.g. "spec: X(...) should raise ValueError('...')"
  notes.py show

Stored under .git/swe_agent/notes.md, which is never part of the patch.
"""
import os
import subprocess
import sys


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


def main():
    args = [a for a in sys.argv[1:] if a != '--']
    path = os.path.join(workspace(), '.git', 'swe_agent', 'notes.md')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if args and args[0] == 'add' and len(args) > 1:
        with open(path, 'a') as f:
            f.write('- ' + ' '.join(args[1:]).strip()[:500] + '\n')
        print('noted')
    if not args or args[0] in ('show', 'add'):
        print(open(path).read() if os.path.exists(path) else '(no notes yet)')
    elif args[0] not in ('show', 'add'):
        print('usage: notes.py add "<finding>" | notes.py show')


if __name__ == '__main__':
    main()
