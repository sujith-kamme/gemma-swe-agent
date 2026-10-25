---
name: rich
description: Module map, test layout and conventions for the Textualize/rich repository (terminal rendering library).
---

# rich repository guide

Package: `rich/` (flat; no src layout). Run Python from `/workspace` as-is.

## PR titles are terse
Typical titles: "fix for padding width", "empty live", "fix infinite loop in append", "Fix ZWJ and edge cases". Map the noun to a module below; the verb tells you the behavior to change.

## Module map (keyword → file)
| Keyword in title | File |
|---|---|
| console, print, export_svg/html/text, capture, width/height detection | `rich/console.py` |
| cell width, cell_len, wide chars, emoji width, ZWJ, unicode width | `rich/cells.py` (data in `rich/_unicode_data/`) |
| segment, split/crop lines, control codes in segments | `rich/segment.py` |
| text, append, append_tokens, highlight, wrap, divide, Text styles | `rich/text.py` (wrapping helpers in `rich/_wrap.py`) |
| markdown, table in markdown, code block, heading, list | `rich/markdown.py` |
| syntax, code highlighting, line numbers, background, padding of code | `rich/syntax.py` |
| table, column, row, box borders | `rich/table.py`, `rich/box.py` |
| panel, title, subtitle | `rich/panel.py` |
| padding | `rich/padding.py` |
| live, refresh, transient | `rich/live.py`, `rich/live_render.py` |
| progress, bars, columns in progress | `rich/progress.py`, `rich/progress_bar.py` |
| traceback, frames, recursion, locals | `rich/traceback.py` |
| pretty, repr of objects, pprint | `rich/pretty.py` |
| markup, [bold] tags, escape | `rich/markup.py` |
| style, color, theme, default styles | `rich/style.py`, `rich/color.py`, `rich/theme.py`, `rich/default_styles.py` |
| ansi decoding | `rich/ansi.py` |
| logging handler | `rich/logging.py` |
| layout, tree, columns, align, rule, prompt, json, emoji, spinner, status | same-named file in `rich/` |
| control codes, cursor movement | `rich/control.py` |

## Tests
- `rich/<module>.py` ↔ `tests/test_<module>.py` (for example `rich/padding.py` → `tests/test_padding.py`).
- Tests render to a string and compare **exact output**, including spaces, newlines and ANSI codes. Common pattern:
  ```python
  console = Console(width=100, color_system=None)   # or file=io.StringIO(), legacy_windows=False
  console.begin_capture(); console.print(obj); out = console.end_capture()
  assert out == "...exact text...\n"
  ```
- `tests/render.py` has a `render(renderable)` helper.
- Check fixes by printing `repr(out)` so that trailing spaces and newlines are visible.

## Conventions
- Keep fixes minimal and inside the module named by the title.
- `CHANGELOG.md` has an "Unreleased" section at the top. Recent entries hint at what is being worked on. Editing it is optional and is not tested.
