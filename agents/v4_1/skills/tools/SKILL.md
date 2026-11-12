---
name: tools
description: Pipeline scripts (candidate pack, editing context, test-and-diff check). Install once with run_skill_script, then run them with run_command.
---

# Tools

Install once (exactly these two arguments, nothing else):
`run_skill_script(skill_name="tools", file_path="scripts/install.py")`

Then run them with `run_command` (they live in .git/swe/, never part of the patch):

| Command | Purpose |
|---|---|
| `timeout 60 python .git/swe/pack.py "<title and key sentence>"` | Best-ranked functions/classes with their code, exact-string hits, related test files |
| `timeout 60 python .git/swe/context.py <path.py::Symbol or path.py:START-END> [...]` | Source of the targets (or a line range), class siblings, usages, existing tests |
| `timeout 115 python .git/swe/check.py --query "<task title>"` | Patch review (PROBLEMS first), then related existing tests in the time left (failures labeled PRE-EXISTING or NEW) |

Every tool prints a [clock] line with the session time left, and keeps its output under the 5000-character command output limit.

Never pass `args` to run_skill_script.
