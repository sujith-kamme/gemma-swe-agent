"""Focused editing context for the chosen edit locations, in one call.

Usage: context.py <path/to/file.py::Symbol> [more targets ...]
       (a target may also be path/to/file.py or path/to/file.py:START-END)

For each target prints the full numbered source of the symbol, the enclosing class header and
the signatures of its sibling methods, and where the symbol is used in non-test code. Then
prints the existing tests that cover it (via tests_for.py): test names and one style example.
"""
import ast
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locate  # noqa: E402

MAX_BODY = 160      # source lines per target
MAX_CHARS = 16000   # whole output


def find_symbol(tree, qual):
    parts = qual.split('.')
    nodes, parent = list(ast.iter_child_nodes(tree)), None
    for i, p in enumerate(parts):
        hit = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and n.name == p), None)
        if hit is None:
            return None, None
        if i < len(parts) - 1:
            parent, nodes = hit, list(ast.iter_child_nodes(hit))
        else:
            return hit, parent
    return None, None


def signature(lines, n):
    sig = lines[n.lineno - 1].strip()
    return f'{n.lineno:5d}  {sig}'


def usages(ws, name, defn_rel, limit=8):
    try:
        r = subprocess.run(['git', 'grep', '-n', '-w', name, '--', '*.py'], cwd=ws, capture_output=True,
                           text=True, timeout=20).stdout.splitlines()
    except Exception:
        return []
    r = [l for l in r if not locate.is_test_path(l.split(':', 1)[0])
         and not re.search(r'\b(def|class)\s+' + re.escape(name) + r'\b', l)]
    return [f'  {l[:170]}' for l in r[:limit]]


def show(ws, target):
    out = []
    path, _, sym = target.partition('::')
    rng = re.match(r'(.+\.py):(\d+)-(\d+)$', path)
    if rng:
        path = rng.group(1)
    full = os.path.join(ws, path)
    if not os.path.isfile(full):
        return [f'!! {path}: file not found']
    src = open(full, encoding='utf-8', errors='replace').read()
    lines = src.splitlines()
    if rng:
        a, b = int(rng.group(2)), int(rng.group(3))
        out.append(f'=== {path}:{a}-{b}')
        out += [f'{i:5d}  {lines[i - 1]}' for i in range(a, min(b, len(lines), a + MAX_BODY - 1) + 1)]
        return out
    if not sym:
        out.append(f'=== {path} (no symbol given: top-level definitions)')
        try:
            tree = ast.parse(src)
            out += [signature(lines, n) for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        except SyntaxError:
            out += [f'{i + 1:5d}  {l}' for i, l in enumerate(lines[:MAX_BODY])]
        return out
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f'!! {path}: cannot parse ({e})']
    node, parent = find_symbol(tree, sym)
    if node is None:
        return [f'!! {sym} not found in {path}; top-level names: ' +
                ', '.join(n.name for n in tree.body if hasattr(n, 'name'))[:400]]
    a, b = node.lineno, getattr(node, 'end_lineno', node.lineno)
    if node.decorator_list:
        a = min(d.lineno for d in node.decorator_list)
    if parent is not None:
        out.append(f'=== class {parent.name} ({path}:{parent.lineno}) header and sibling methods:')
        out.append(f'{parent.lineno:5d}  {lines[parent.lineno - 1].strip()}')
        out += [signature(lines, n) for n in parent.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not node]
    out.append(f'=== {path}::{sym}  lines {a}-{b}')
    shown = range(a, min(b, a + MAX_BODY - 1) + 1)
    out += [f'{i:5d}  {lines[i - 1]}' for i in shown]
    if b > shown[-1]:
        out.append(f'  ... ({b - shown[-1]} more lines: read_file to see them)')
    u = usages(ws, node.name, path)
    if u:
        out.append(f'--- {node.name} used in (non-test):')
        out += u
    return out


def main():
    targets = [a for a in sys.argv[1:] if a != '--']
    if not targets:
        print(__doc__)
        return
    ws = locate.workspace()
    out = []
    for t in targets[:4]:
        out += show(ws, t)
        out.append('')
    tf = [t.partition('::')[0].split(':')[0] for t in targets[:2]]
    syms = [t.partition('::')[2].split('.')[-1] for t in targets[:2] if '::' in t]
    try:
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests_for.py'),
                            *tf, *syms], cwd=ws, capture_output=True, text=True, timeout=60)
        out.append('=== Existing tests for these targets:')
        out += r.stdout.strip().splitlines()
    except Exception as e:
        out.append(f'(tests_for failed: {e})')
    text = '\n'.join(out)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + '\n... (truncated)'
    print(text)


if __name__ == '__main__':
    main()
