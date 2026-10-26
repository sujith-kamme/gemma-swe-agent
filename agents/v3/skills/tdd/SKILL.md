---
name: tdd
description: Write the failing test first, in the style of the project's existing tests, and run it safely. Finds the right test file and shows its style.
---

# Test first: reproduce the task as a test

The grader adds new tests to an EXISTING test file and runs that whole file. Write the same kind of test yourself
before changing code. It must FAIL (or TIMEOUT) now, for the reason the task describes.

## 1. Find the existing tests and their style
`timeout 60 python .git/swe/tests_for.py <path/to/module.py> <SymbolName>`
Shows the most relevant test files, test names, one short test as a style example, its imports, and the pytest command.
Test files are not always named after the module; this script searches by imports and mentions.

## 2. Write one small test that encodes the acceptance criterion
- Same imports, fixtures and assertion style as the example (exact `==` comparisons, `pytest.raises(..., match=...)`,
  `response.status_code` and `response.json()`, captured console output — whatever the file uses).
- Assert the exact expected value from the task, not just "no exception".
- One behavior per test. 5–15 lines.

## 3. Run it (never in the repository's own test files)
Write it with `write_file(filepath=".git/swe/test_repro.py", content="<test code>")`, then run
`timeout 60 python .git/swe/try_test.py .git/swe/test_repro.py --near <existing test file>`
- Copies the test next to the existing file (so its conftest fixtures work), runs it with a 30 s timeout, deletes the copy.
- RESULT: FAILED or TIMEOUT for the right reason means you reproduced the task. PASSED means your test does not capture
  the problem: re-read the task and fix the test (max 2 tries, then continue with your best understanding).
- After your fix, the same command must give RESULT: PASSED.

Never add or edit files under tests/ in the final patch — the grader discards them. The scripts clean up after themselves.
