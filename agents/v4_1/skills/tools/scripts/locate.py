"""Rank functions/classes in the repository by relevance to a task description.

Usage: locate.py "<task text or keywords>" [--k 12]

Scores every function and class in non-test Python files with BM25 over
identifiers, string literals and docstrings. Code-like tokens from the query
(backticked text, CamelCase, snake_case, dotted names, quoted strings) weigh more
than plain words. Prints the best symbols with file:line ranges, the best files,
and test files that mention the top symbols.
"""
import ast
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict

SKIP_DIRS = {'.git', '.hg', '.tox', '.venv', 'venv', 'env', 'node_modules', 'build', 'dist',
             '__pycache__', 'site-packages', '.mypy_cache', '.pytest_cache', '.eggs'}
STOP = set('''a an and are as at be but by can could do does for from has have how if in into is it its
of on or our should so than that the their then there these this to was we were what when where which
while who why will with would not no yes fix fixes fixed add adds added support use using used allow
allows make makes new now also when issue issues bug pr change changes update updates type types
github com https http www pull closes close see like just only some more less get set via'''.split())
OUT_CHARS = 4800    # the harness keeps only the first 5000 characters of a command's output
BUDGET_S = 300      # session time limit (eval_config.yaml max_time_minutes: 5)


def workspace():
    cands = [os.environ.get('SWE_WORKSPACE'), '/workspace', os.getcwd(), os.environ.get('HOME')]
    for c in cands:
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


def elapsed(ws):
    """Seconds since install.py ran, or None."""
    try:
        return int(time.time() - float(open(os.path.join(ws, '.git', 'swe', 't0')).read()))
    except Exception:
        return None


def clock(ws):
    """One line with the time used since install.py ran: the model has no clock of its own."""
    used = elapsed(ws)
    if used is None:
        return ''
    left = BUDGET_S - used
    note = ''
    if left < 90:
        note = ' Time is almost up: submit_patch now.'
    elif left < 170:
        note = ' Time is short: make your best edit now (an edit left in the files is still graded).'
    return f'[clock: about {used} s used, {max(left, 0)} s left of {BUDGET_S} s.{note}]'


READ_LIMIT_S = 150  # after this, the reading tools stop until something is edited


def edited(ws):
    """True when a tracked file outside the environment's own pre-existing changes is modified
    (new untracked files are usually scratch scripts, so they do not count)."""
    try:
        baseline = set(open(os.path.join(ws, '.git', 'swe', 'baseline')).read().splitlines())
    except Exception:
        baseline = set()
    try:
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=ws, capture_output=True, text=True,
                                timeout=20).stdout.splitlines()
    except Exception:
        return True
    return any(not l.startswith('??') and l[3:].strip().strip('"') not in baseline for l in status)


def reading_closed(ws):
    """The model does not act on the clock by itself, so the reading tools enforce it: past
    READ_LIMIT_S with nothing edited they print an instruction to edit instead of more code."""
    used = elapsed(ws)
    if used is None or used < READ_LIMIT_S or edited(ws):
        return ''
    return (f'{clock(ws)}\nREADING IS CLOSED: {used} s used and nothing is edited yet. Make your best edit now '
            'with edit_file, using the code you have already seen. An edit is graded even if it is imperfect; '
            'no edit always scores zero. The checker reviews the edit after you.')


def split_ident(tok):
    parts = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', tok).replace('_', ' ').replace('.', ' ').split()
    return [p.lower() for p in parts if len(p) > 1]


def query_terms(text):
    weights = Counter()
    for m in re.findall(r'`([^`]+)`', text):
        for t in re.findall(r'[A-Za-z_][A-Za-z0-9_.]*', m):
            weights[t.lower()] += 3
            for p in split_ident(t):
                weights[p] += 1
    for m in re.findall(r'["\']([^"\']{3,60})["\']', text):
        for p in re.findall(r'[A-Za-z_][A-Za-z0-9_]+', m):
            weights[p.lower()] += 1
    for t in re.findall(r'[A-Za-z_][A-Za-z0-9_.]*', text):
        low = t.lower().strip('.')
        if low in STOP or len(low) < 3:
            continue
        code_like = ('_' in t or '.' in t.strip('.') or re.search(r'[a-z][A-Z]', t) or t[:1].isupper() and t[1:].lower() != t[1:])
        weights[low] += 2 if code_like else 1
        if code_like:
            for p in split_ident(t):
                if p not in STOP:
                    weights[p] += 1
    return weights


def is_test_path(rel):
    parts = rel.split('/')
    name = parts[-1]
    return (any(p in ('tests', 'test', 'testing') for p in parts[:-1])
            or name.startswith('test_') or name.endswith('_test.py') or name == 'conftest.py')


def iter_py(ws):
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if f.endswith('.py'):
                full = os.path.join(root, f)
                yield os.path.relpath(full, ws), full


def chunk_tokens(node, src_lines):
    toks = Counter()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            toks[sub.id.lower()] += 1
            for p in split_ident(sub.id):
                toks[p] += 1
        elif isinstance(sub, ast.Attribute):
            toks[sub.attr.lower()] += 1
            for p in split_ident(sub.attr):
                toks[p] += 1
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            for w in re.findall(r'[A-Za-z_][A-Za-z0-9_]+', sub.value[:300]):
                toks[w.lower()] += 1
        elif isinstance(sub, ast.arg):
            toks[sub.arg.lower()] += 1
    return toks


def collect(ws):
    chunks = []  # (rel, qualname, start, end, tokens, name_tokens)
    for rel, full in iter_py(ws):
        if is_test_path(rel):
            continue
        try:
            src = open(full, encoding='utf-8', errors='replace').read()
            tree = ast.parse(src)
        except Exception:
            continue
        lines = src.splitlines()

        def visit(node, prefix):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    q = f'{prefix}{ch.name}'
                    name_toks = Counter([ch.name.lower()] + split_ident(ch.name) + split_ident(rel[:-3].replace('/', '.')))
                    if isinstance(ch, ast.ClassDef):
                        # class header only (methods are separate chunks)
                        head = Counter()
                        for b in ch.bases:
                            for t in re.findall(r'[A-Za-z_]+', ast.unparse(b) if hasattr(ast, 'unparse') else ''):
                                head[t.lower()] += 1
                        doc = ast.get_docstring(ch) or ''
                        for w in re.findall(r'[A-Za-z_][A-Za-z0-9_]+', doc[:500]):
                            head[w.lower()] += 1
                        chunks.append((rel, q, ch.lineno, getattr(ch, 'end_lineno', ch.lineno), head, name_toks))
                        visit(ch, q + '.')
                    else:
                        chunks.append((rel, q, ch.lineno, getattr(ch, 'end_lineno', ch.lineno),
                                       chunk_tokens(ch, lines), name_toks))
        visit(tree, '')
    return chunks


def bm25(chunks, q):
    N = len(chunks) or 1
    df = Counter()
    for c in chunks:
        for t in set(c[4]) | set(c[5]):
            df[t] += 1
    avg = sum(sum(c[4].values()) for c in chunks) / N or 1
    k1, b = 1.2, 0.75
    out = []
    for c in chunks:
        dl = sum(c[4].values()) or 1
        s = 0.0
        hits = []
        for t, w in q.items():
            tf = c[4].get(t, 0)
            nt = c[5].get(t, 0)
            if not tf and not nt:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += w * idf * (tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avg)) + 2.0 * min(nt, 2))
            hits.append(t)
        if s > 0:
            out.append((s, c, hits))
    out.sort(key=lambda x: -x[0])
    return out


def related_tests(ws, symbols, limit=6):
    counts = Counter()
    for rel, full in iter_py(ws):
        if not is_test_path(rel) or rel.endswith('conftest.py'):
            continue
        try:
            txt = open(full, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        for s in symbols:
            n = len(re.findall(r'\b' + re.escape(s) + r'\b', txt))
            if n:
                counts[rel] += n
    return counts.most_common(limit)


def main():
    args = [a for a in sys.argv[1:] if a != '--']
    k = 12
    if '--k' in args:
        i = args.index('--k')
        k = int(args[i + 1])
        del args[i:i + 2]
    text = ' '.join(args).strip()
    if not text:
        print('usage: locate.py "<task text or keywords>" [--k 12]')
        return
    ws = workspace()
    q = query_terms(text)
    chunks = collect(ws)
    ranked = bm25(chunks, q)[:k]
    print(f'query terms: {", ".join(t for t, _ in q.most_common(15))}')
    print('\nTop symbols (file:start-end  symbol  [matched terms]):')
    for s, c, hits in ranked:
        print(f'  {c[0]}:{c[2]}-{c[3]}  {c[1]}  [{", ".join(sorted(set(hits))[:6])}]  score={s:.1f}')
    files = defaultdict(float)
    for s, c, _ in bm25(chunks, q)[:60]:
        files[c[0]] += s
    print('\nTop files:')
    for f, s in sorted(files.items(), key=lambda x: -x[1])[:6]:
        print(f'  {f}  score={s:.1f}')
    syms = []
    for _, c, _ in ranked[:5]:
        name = c[1].split('.')[-1]
        if name not in syms and len(name) > 3:
            syms.append(name)
    rt = related_tests(ws, syms)
    if rt:
        print(f'\nTest files mentioning {", ".join(syms)}:')
        for f, n in rt:
            print(f'  {f}  ({n} mentions)')
    print('\nThis ranking is lexical. Confirm by reading the code path from the public API that the task names.')


if __name__ == '__main__':
    main()
