---
name: verify
description: After editing, prove the fix and check for regressions, then review the patch before submit_patch.
---

# Verify: prove it, check regressions, review, submit

1. **Your test passes.**
   `timeout 60 python .git/swe/try_test.py .git/swe/test_repro.py --near <existing test file>` must print RESULT: PASSED.
2. **Existing tests still pass.**
   `timeout 120 python .git/swe/run_tests.py`
   (or pass test files explicitly). Every failing test is labeled:
   - PRE-EXISTING: fails without your change too. Ignore it.
   - NEW: passes without your change. Fix your code — unless the task explicitly asks for that behavior change, in which
     case the hidden tests expect the new behavior and the old test will be updated by the grader.
   - COLLECTION ERROR with a missing module: environment issue, not yours.
3. **Review the patch.**
   `timeout 60 python .git/swe/check_diff.py`
   Fix every PROBLEM it lists (scratch files, debug prints, edited tests, empty diff).
4. **Submit.** Call `submit_patch`, then reply with one line describing the change.

If time or tool calls are running low (budget warnings), skip to steps 3–4: a reasonable patch scores, an empty one never does.
