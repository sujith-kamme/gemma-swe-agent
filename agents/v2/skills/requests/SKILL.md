---
name: requests
description: Module map, src layout notes and test layout for the psf/requests repository.
---

# requests repository guide

Package: `src/requests/` (**src layout**). When you run Python yourself, use `PYTHONPATH=src python ...` so that your edits are what gets imported.

## Module map (keyword → file)
| Keyword in title | File |
|---|---|
| headers parsing, content-type, netrc, proxies, URL helpers, encodings, `_parse_*` helpers, super_len | `src/requests/utils.py` |
| Request/Response/PreparedRequest, body encoding, files, `_encode_files`, json, iter_content | `src/requests/models.py` |
| sessions, redirects, merge settings, auth on redirect | `src/requests/sessions.py` |
| adapters, connection pools, request_url, TLS/certs, retries | `src/requests/adapters.py` |
| auth (Basic/Digest) | `src/requests/auth.py` |
| cookies | `src/requests/cookies.py` |
| compat shims, typing protocols | `src/requests/compat.py`, `src/requests/_types.py` |
| exceptions | `src/requests/exceptions.py` |
| case-insensitive dict | `src/requests/structures.py` |

## Tests
- `tests/test_utils.py` (utils), `tests/test_requests.py` (models, sessions, most behavior), `tests/test_lowlevel.py` (raw socket server), `tests/test_adapters.py`, `tests/test_structures.py`.
- Many tests are parametrized tables. Add a case to the matching table style when you reason about expected behavior.

## Conventions
- Small, conservative fixes. Preserve backward compatibility.
- PR descriptions often state the exact intended behavior (e.g. "skip value assignment if malformed"). Implement exactly that.
