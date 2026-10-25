---
name: fastapi
description: Module map, test layout, docs_src tutorials and conventions for the fastapi/fastapi repository.
---

# fastapi repository guide

Package: `fastapi/` (flat; no src layout). Run Python from `/workspace` as-is.

## Title emoji = change type (gitmoji)
🐛 bug fix · ✨ new feature · 📝 docs/tutorial change · ♻️ refactor · 🔒️ security · ⬆️ dependency upgrade · ➖ drop a dependency · 🎨 style/typing.
For ✨ features, the hidden tests usually exercise the new API directly and often also a new or updated **tutorial file** in `docs_src/`.

## Module map (keyword → file)
| Keyword in title | File |
|---|---|
| Depends, dependencies, yield dependencies, scopes, parameters, Query/Path/Header/Cookie/Body/Form/File resolution, request parsing, validation of params | `fastapi/dependencies/utils.py` (models in `fastapi/dependencies/models.py`) |
| routes, APIRouter, APIRoute, path operations, response handling, include_router, streaming, websocket routes | `fastapi/routing.py` |
| Pydantic v2 compat, field info, schema generation helpers, aliases | `fastapi/_compat/v2.py`, `fastapi/_compat/shared.py` |
| OpenAPI schema, openapi.json, $ref, components, JSON Schema | `fastapi/openapi/utils.py` (models in `fastapi/openapi/models.py`, docs UI in `fastapi/openapi/docs.py`) |
| FastAPI app class, app-level options, lifespan, exception handlers registration | `fastapi/applications.py` |
| Query(), Path(), Body() signatures and params | `fastapi/param_functions.py`, `fastapi/params.py` |
| security, OAuth2, API key, HTTP auth, 401/403 | `fastapi/security/*.py` |
| JSON encoding, jsonable_encoder | `fastapi/encoders.py` |
| exceptions, HTTPException, validation errors | `fastapi/exceptions.py`, `fastapi/exception_handlers.py` |
| responses, JSONResponse, StreamingResponse | `fastapi/responses.py` (+ `routing.py`) |
| middleware | `fastapi/middleware/*.py` |
| UploadFile, datastructures | `fastapi/datastructures.py` |
| generic helpers | `fastapi/utils.py` |

## Tests
- Feature and bug tests: `tests/test_<topic>.py` (flat, many files, e.g. `tests/test_dependency_yield_scope.py`). Grep for the topic: `ls tests | grep -i <keyword>`.
- Parameter tests: `tests/test_request_params/`.
- **Tutorial tests**: `docs_src/<section>/tutorialNNN_py310.py` ↔ `tests/test_tutorial/test_<section>/test_tutorialNNN.py`. They import the app with `from docs_src.<section>.<file> import app` and call it via `TestClient`.
- If the task changes documented behavior or an example, update the matching `docs_src/` file(s). If a hidden test could import a tutorial module that does not exist yet (new feature), create it in `docs_src/<section>/` following the sibling files (variants `_py39`, `_py310`, `_an_py310` = Annotated).
- Tests compare exact `response.json()` and exact OpenAPI JSON. Error messages must match exactly.

## Conventions
- Error and assertion messages follow existing patterns. Grep for similar messages (`grep -rn "must be" fastapi/ | head`) and copy their wording style.
- Keep typing annotations consistent with the surrounding code.
- Check fixes with a tiny app: `python -c "from fastapi import FastAPI; from fastapi.testclient import TestClient; ..."`.
