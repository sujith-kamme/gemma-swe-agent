---
name: triage
description: Turn the task text into a precise, testable acceptance criterion. Use first, on every task, especially when the text is short or vague.
---

# Triage: decide exactly what must change

The task text is the title and description of a merged pull request (sometimes an issue).
Linked issues (#123, URLs) cannot be opened. Work from the text and the code.

## 1. Classify the change
| Signal in the text | Kind | What the hidden tests usually do |
|---|---|---|
| "fix", "bug", "error", "crash", "wrong", "infinite", "regression" | Bug fix | Call the public API with the failing input and assert the correct result |
| "add", "support", "new", "allow", "introduce", "option" | Feature | Call the NEW parameter/function/class by an exact name and assert its behavior |
| "change", "rename", "deprecate", "use X instead of Y", "default" | Behavior change | Existing tests are updated to expect the new behavior |
| "refactor", "typing", "cleanup" | Refactor | Behavior stays the same; existing tests must keep passing |
| examples, tutorials, docs code | Example change | Tests import the example module and check its output |

## 2. Write the acceptance criterion
One or two lines, in this shape:

    calling <public API>(<input from the text>) should <return / print / raise> <exact result>

- Use exact names, option values, messages and status codes that appear in the text. Copy them character for character.
- For terse titles ("empty live", "padding width"): name the object and the operation, then decide what "correct" means
  for it (no crash, right width, no hang, same as the similar working case).
- For features with no name given: the name will follow the patterns of sibling code (look at how similar options,
  parameters or helpers are named nearby) — never invent a style of your own.
- About half of the hidden tests compare exact output (strings, rendered text, JSON, status codes). Precision matters
  more than elegance.

## 3. Save it
`run_skill_script(skill_name="notes", file_path="scripts/notes.py", args=["add", "spec: <criterion>"])`
