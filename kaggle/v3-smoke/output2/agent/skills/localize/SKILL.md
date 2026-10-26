---
name: localize
description: Find the code that actually produces the behavior in the task by tracing from the public API, not by matching file names. Uses the locate tool.
---

# Localize: find where the behavior is produced

A word in the title is not a location. "padding width" may be fixed in a table, "append" in `append_tokens`.
Find the code path that runs for the input in your acceptance criterion.

## Methods (use in this order, stop when confirmed)
1. **Exact strings first.** Error messages, option names, CLI flags, literal values quoted in the task:
   `grep -rn "<exact string>" --include=*.py . | grep -v tests | head`
2. **Rank candidates.**
   `timeout 60 python .git/swe/locate.py "<title and key sentence>"` (tools installed, see the `tools` skill)
   Prints the best functions with file:line ranges, best files, and related test files. It is lexical: use it to pick
   what to read, not as proof.
3. **Trace from the public API.** Start at the function/class the task names (or that a user would call), then follow
   calls downward:
   - `get_code_neighbors(node="Class.method")` lists callers and callees.
   - `search_similar_code(query="Class.method")` finds related implementations (sibling code to copy patterns from).
   - Read only the function you need: `read_file(filepath=..., start_line=..., end_line=...)`.
4. **Confirm.** The location is right when you can say which line produces the wrong result for the criterion's input.
   A failing test's traceback (see the `tdd` skill) is the best confirmation.

## Rules
- Read with line ranges. Never read the same range twice; write findings to notes instead.
- Prefer the deepest shared function that all affected callers go through, but do not change unrelated callers.
- If two candidates remain, pick the one the traceback or a quick print shows is executed.
- Save: `python .git/swe/notes.py add "location: <file>:<line> <function> because <reason>"`
