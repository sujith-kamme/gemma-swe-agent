"""Find the existing tests that cover a source file or symbol, and show their style.

Usage: tests_for.py <path/to/module.py | SymbolName> [more targets ...] [--query "<task title>"]

Ranks test files two ways and fuses the rankings: (1) how often they import the
module or mention the symbols, (2) how well their file names and test names match
the task text (tests are often named after the feature, not the module). Lists
test names in the best file, prints one short test as a style example, and gives
the pytest command to run them.
"""
import ast
import math
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
    name = rel.split('/')[-1]
    return name.endswith('.py') and (name.startswith('test_') or name.endswith('_test.py'))


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


STOP = set('''the and for with from that this into when then than not are was were has have use used using add adds
added support fix fixes fixed allow make new now also issue bug change changes update type types test tests should
can could would will does via all any its get set'''.split())


def words(text):
    out = []
    for t in re.findall(r'[A-Za-z][A-Za-z0-9_]*', text):
        t = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', t)  # HTTPBearer -> HTTP Bearer
        for p in re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', t).replace('_', ' ').split():
            p = p.lower()
            if len(p) >= 3 and p not in STOP:
                out.append(p[:-1] if p.endswith('s') and len(p) > 4 else p)
    return out


def rank_by_query(ws, files, query):
    q = Counter(words(query))
    scores = Counter()
    for rel, txt in files.items():
        name = Counter(words(os.path.splitext(rel)[0]))
        tnames = Counter(w for n in re.findall(r'def (test_\w+)', txt) for w in words(n[5:]))
        s = sum(w * (6 * min(name[t], 1) + min(tnames[t], 4)) for t, w in q.items())
        if s:
            scores[rel] = s
    return scores


def fuse(*rankings):
    out = Counter()
    for sc in rankings:
        for i, (rel, _) in enumerate(sc.most_common()):
            out[rel] += 1.0 / (5 + i)
    return out


def rank(ws, targets, query=''):
    """Rank test files for source targets and/or a task-text query. Returns (patterns, stems, scores, contents)."""
    patterns, stems = [], []
    for t in targets:
        if t.endswith('.py') and os.path.exists(os.path.join(ws, t)):
            names, stem = module_names(ws, t)
            stems.append(stem)
            for n in names:
                if '.' in n:
                    patterns.append((re.compile(r'(from|import)\s+' + re.escape(n) + r'\b'), 5))
            try:
                tree = ast.parse(open(os.path.join(ws, t), encoding='utf-8', errors='replace').read())
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                        patterns.append((re.compile(r'\b' + re.escape(node.name) + r'\b'), 1))
            except Exception:
                pass
        else:
            patterns.append((re.compile(r'\b' + re.escape(t.split('.')[-1]) + r'\b'), 3))
    contents, counts = {}, {}
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), ws)
            if not is_test_file(rel):
                continue
            try:
                txt = open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            contents[rel] = txt
            counts[rel] = [min(len(p.findall(txt)), 20) for p, _ in patterns]
    # down-weight patterns that most test files share (e.g. a core module every test imports)
    n = len(contents) or 1
    df = [sum(1 for c in counts.values() if c[i]) for i in range(len(patterns))]
    idf = [math.log((n + 1) / (d + 1)) for d in df]
    scores = Counter()
    for rel, c in counts.items():
        sc = sum(w * idf[i] * c[i] for i, (_, w) in enumerate(patterns))
        if any(st and st in os.path.basename(rel) for st in stems):
            sc += 15
        if sc > 0:
            scores[rel] = sc
    if query:
        q = rank_by_query(ws, contents, query)
        scores = fuse(scores, q) if scores else q
    return patterns, stems, scores, contents


def main():
    args = [a for a in sys.argv[1:] if a != '--']
    query = ''
    if '--query' in args:
        i = args.index('--query')
        query = ' '.join(args[i + 1:i + 2])
        del args[i:i + 2]
    targets = args
    if not targets and not query:
        print('usage: tests_for.py <path/to/module.py | SymbolName> [...] [--query "<task title>"]')
        return
    ws = workspace()
    patterns, stems, scores, contents = rank(ws, targets, query)
    if not scores:
        print('No test file mentions these targets. Look for tests of the calling code instead (grep the public API name in the test directory).')
        return
    best = scores.most_common(6)
    print('Test files (most relevant first):')
    for rel, s in best:
        print(f'  {rel}  score={s:.3g}')
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
