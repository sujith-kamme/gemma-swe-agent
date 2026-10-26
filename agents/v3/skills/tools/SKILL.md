---
name: tools
description: Engineering tools (locate code, find related tests, run a throwaway test, run existing tests, review the diff, notes). Install once with run_skill_script, then use them with run_command.
---

# Tools

Install once (exactly these two arguments, nothing else):
`run_skill_script(skill_name="tools", file_path="scripts/install.py")`

Then use them through `run_command` (all live in .git/swe/, never part of the patch):

| Command | Purpose |
|---|---|
| `timeout 60 python .git/swe/locate.py "<title and key sentence>"` | Rank functions/files by relevance to the task; lists related test files |
| `timeout 60 python .git/swe/tests_for.py <path/to/module.py> <Symbol>` | Existing tests covering that code, one style example, imports, run command |
| `write_file(filepath=".git/swe/test_repro.py", content="<pytest test>")` | Write a throwaway test (outside the patch) |
| `timeout 60 python .git/swe/try_test.py .git/swe/test_repro.py --near <existing test file>` | Run it next to the real tests (conftest fixtures work), 30 s limit, RESULT: PASSED/FAILED/TIMEOUT |
| `timeout 120 python .git/swe/run_tests.py [test files]` | Run related existing tests; failures labeled PRE-EXISTING or NEW |
| `timeout 60 python .git/swe/check_diff.py` | Review the patch: flags scratch files, debug prints, edited tests, empty diff |
| `python .git/swe/notes.py add "<finding>"` / `python .git/swe/notes.py show` | Notes that survive context summaries |

Never pass `args` to run_skill_script.
