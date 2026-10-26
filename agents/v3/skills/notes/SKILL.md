---
name: notes
description: A persistent notebook for findings (spec, location, test, status). Survives context summaries; read it instead of re-exploring.
---

# Notes

Long sessions get summarized and details are lost. Write each key finding once, and read the notes when you feel lost
instead of re-reading files or re-running searches.

- Add: `run_skill_script(skill_name="notes", file_path="scripts/notes.py", args=["add", "<one line>"])`
- Show: `run_skill_script(skill_name="notes", file_path="scripts/notes.py", args=["show"])`

Good notes: `spec: ...`, `location: file:line function because ...`, `test: repro fails with ...`,
`edit: changed ... in file:line`, `status: repro passes, run_tests clean, next: submit`.
Notes live in .git/swe_agent/ and are never part of the patch.
