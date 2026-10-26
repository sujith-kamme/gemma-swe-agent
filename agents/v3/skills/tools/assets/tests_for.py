"""Find the existing tests that cover a source file or symbol, and show their style.

Usage: tests_for.py <path/to/module.py | SymbolName> [more targets ...]

Ranks test files by how often they import the module or mention the symbols,
lists test function names in the best file, prints one short test as a style
example, and gives the pytest command to run them.
"""
import ast
import os
import re
import subprocess
import sys
from collections import Counter

SKIP_DIRS = {'.git', '.tox', '.venv', 'venv', 'env', 'node_modules', 'build', 'dist', '__pycache__', 'site-packages'}


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


def is_test_file(rel):
    parts = rel.split('/')
    name = parts[-1]
    return name.endswith('.py') and name != 'conftest.py' and (
        name.startswith('test_') or name.endswith('_test.py') or any(p in ('tests', 'test', 'testing') for p in parts[:-1]))


def module_names(ws, path):
    rel = os.path.relpath(os.path.join(ws, path), ws)[:-3]
    parts = rel.split('/')
    if parts and parts[0] == 'src':
        parts = parts[1:]
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    dotted = '.'.join(parts)
    names = {dotted}
    if parts:
        names.add(parts[-1])
    return names, parts[-1] if parts else ''


def main():
    targets = [a for a in sys.argv[1:] if a != '--']
    if not targets:
        print('usage: tests_for.py <path/to/module.py | SymbolName> [...]')
        return
    ws = workspace()
    patterns = []
    stems = []
    for t in targets:
        if t.endswith('.py') and os.path.exists(os.path.join(ws, t)):
            names, stem = module_names(ws, t)
            stems.append(stem)
            for n in names:
                if '.' in n:
                    patterns.append((re.compile(r'(from|import)\s+' + re.escape(n) + r'\b'), 5))
            # also symbols defined at top level of that module
            try:
                tree = ast.parse(open(os.path.join(ws, t), encoding='utf-8', errors='replace').read())
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                        patterns.append((re.compile(r'\b' + re.escape(node.name) + r'\b'), 1))
            except Exception:
                pass
        else:
            sym = t.split('.')[-1]
            patterns.append((re.compile(r'\b' + re.escape(sym) + r'\b'), 3))
    scores = Counter()
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, ws)
            if not is_test_file(rel):
                continue
            try:
                txt = open(full, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            s = sum(w * min(len(p.findall(txt)), 20) for p, w in patterns)
            if any(st and st in f for st in stems):
                s += 15
            if s:
                scores[rel] += s
    if not scores:
        print('No test file mentions these targets. Look for tests of the calling code instead (grep the public API name in the test directory).')
        return
    best = scores.most_common(6)
    print('Test files (most relevant first):')
    for rel, s in best:
        print(f'  {rel}  score={s}')
    top = best[0][0]
    src = open(os.path.join(ws, top), encoding='utf-8', errors='replace').read()
    try:
        tree = ast.parse(src)
        tests = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test')]
    except Exception:
        tests = []
    lines = src.splitlines()
    if tests:
        print(f'\n{top} has {len(tests)} tests. Names (sample): ' + ', '.join(t.name for t in tests[:25]))
        relevant = [t for t in tests if any(p.search('\n'.join(lines[t.lineno - 1:t.end_lineno])) for p, w in patterns)] or tests
        short = sorted(relevant, key=lambda t: (t.end_lineno - t.lineno))[: max(1, len(relevant) // 3)]
        ex = short[-1]
        print(f'\nStyle example ({top}:{ex.lineno}):')
        print('\n'.join(lines[ex.lineno - 1:min(ex.end_lineno, ex.lineno + 30)]))
        imports = [l for l in lines[:60] if l.startswith(('import ', 'from '))]
        print('\nImports used by that file:\n' + '\n'.join(imports[:20]))
    print(f'\nRun: timeout 90 python -m pytest {top} -q -x -p no:cacheprovider 2>&1 | tail -20')


if __name__ == '__main__':
    main()
