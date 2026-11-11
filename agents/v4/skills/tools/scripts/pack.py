"""Candidate pack for localization: the best-ranked functions/classes WITH their code, in one call.

Usage: pack.py "<task title and key sentence>" [--k 8]

Ranks every function and class in non-test files (same BM25 ranking as locate.py), then prints
for each candidate its file:line range and the first lines of its code. Also prints exact-string
hits for identifiers and quoted text from the task, the top files, and the test files that
mention the top symbols. Read the pack, then pick where to edit.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locate  # noqa: E402

MAX_LINES = 30      # code lines shown per candidate
MAX_CHARS = 14000   # whole pack


def exact_hits(ws, text, limit=12):
    terms = []
    for m in re.findall(r'`([^`]{3,80})`', text) + re.findall(r'["\']([^"\']{4,60})["\']', text):
        if m not in terms:
            terms.append(m)
    for t in re.findall(r'\b[A-Za-z_]*[a-z][A-Z_][A-Za-z0-9_]*\b|\b[a-z]+_[a-z0-9_]+\b', text):
        if t not in terms:
            terms.append(t)
    out = []
    for t in terms[:6]:
        try:
            r = subprocess.run(['git', 'grep', '-n', '-F', t, '--', '*.py'], cwd=ws, capture_output=True,
                               text=True, timeout=20).stdout.splitlines()
        except Exception:
            continue
        r = [l for l in r if not locate.is_test_path(l.split(':', 1)[0])][:4]
        out += [f'  [{t}] {l[:160]}' for l in r]
    return out[:limit]


def main():
    args = [a for a in sys.argv[1:] if a != '--']
    k = 8
    if '--k' in args:
        i = args.index('--k')
        k = int(args[i + 1])
        del args[i:i + 2]
    text = ' '.join(args).strip()
    if not text:
        print('usage: pack.py "<task title and key sentence>" [--k 8]')
        return
    ws = locate.workspace()
    q = locate.query_terms(text)
    chunks = locate.collect(ws)
    ranked = locate.bm25(chunks, q)
    out = [f'query terms: {", ".join(t for t, _ in q.most_common(12))}']
    hits = exact_hits(ws, text)
    if hits:
        out.append('\nExact matches in source (term, file:line):')
        out += hits
    files = {}
    for s, c, _ in ranked[:60]:
        files[c[0]] = files.get(c[0], 0) + s
    out.append('\nTop files: ' + ', '.join(f for f, _ in sorted(files.items(), key=lambda x: -x[1])[:6]))
    out.append(f'\nTop {k} candidates (lexical ranking: confirm against the task, do not trust blindly):')
    seen = 0
    for s, c, hit in ranked:
        if seen >= k:
            break
        rel, qual, start, end = c[0], c[1], c[2], c[3]
        try:
            lines = open(os.path.join(ws, rel), encoding='utf-8', errors='replace').read().splitlines()
        except Exception:
            continue
        seen += 1
        body = lines[start - 1:min(end, start - 1 + MAX_LINES)]
        more = f'  ... ({end - start + 1 - len(body)} more lines)' if end - start + 1 > len(body) else ''
        out.append(f'\n#{seen} {rel}:{start}-{end}  {qual}  [{", ".join(sorted(set(hit))[:6])}]')
        out += [f'{start + i:5d}  {l}' for i, l in enumerate(body)]
        if more:
            out.append(more)
    syms = []
    for _, c, _ in ranked[:5]:
        name = c[1].split('.')[-1]
        if name not in syms and len(name) > 3:
            syms.append(name)
    rt = locate.related_tests(ws, syms, limit=4)
    if rt:
        out.append('\nTest files mentioning top symbols: ' + ', '.join(f for f, _ in rt))
    text_out = '\n'.join(out)
    if len(text_out) > MAX_CHARS:
        text_out = text_out[:MAX_CHARS] + '\n... (pack truncated)'
    print(text_out)


if __name__ == '__main__':
    main()
