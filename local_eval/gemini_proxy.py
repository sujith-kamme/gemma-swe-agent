"""Local OpenAI-compatible proxy: harness -> Google AI Studio (hosted Gemma 4).

The harness sends vLLM-only request fields (chat_template_kwargs,
thinking_token_budget) that Google's OpenAI endpoint rejects with 400. This
proxy strips them, rewrites the model name, and forwards everything else.

Usage: .venv/bin/python local_eval/gemini_proxy.py [--port 8787]
Then point the harness at OPENAI_BASE_URL=http://127.0.0.1:8787/v1.
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = "https://generativelanguage.googleapis.com/v1beta/openai"
UPSTREAM_MODEL = "gemma-4-31b-it"
DROP_KEYS = {"chat_template_kwargs", "thinking_token_budget", "skip_special_tokens",
             "include_stop_str_in_output", "top_k", "min_p", "repetition_penalty"}
# Free tier rate limits: keep requests spaced and retry 429/5xx.
MIN_INTERVAL_S = float(os.environ.get("PROXY_MIN_INTERVAL", "2.0"))
MAX_RETRIES = 6

_lock = threading.Lock()
_last = [0.0]
_stats = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "errors": 0}


def load_key() -> str:
    env = Path(__file__).resolve().parent.parent / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("GEMINI_API_KEY missing from .env")


def throttle() -> None:
    with _lock:
        wait = _last[0] + MIN_INTERVAL_S - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


class Handler(BaseHTTPRequestHandler):
    key = ""

    def log_message(self, fmt, *args):  # quiet default access log
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({"object": "list", "data": [{"id": UPSTREAM_MODEL, "object": "model"}]}).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b"{}", "application/json")

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            return self._send(400, b'{"error":"bad json"}', "application/json")
        for k in DROP_KEYS:
            req.pop(k, None)
        req["model"] = UPSTREAM_MODEL
        stream = bool(req.get("stream"))
        data = json.dumps(req).encode()
        sub = self.path.split("/v1", 1)[-1] or "/chat/completions"

        for attempt in range(MAX_RETRIES):
            throttle()
            upstream = urllib.request.Request(
                UPSTREAM + sub, data=data, method="POST",
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            try:
                resp = urllib.request.urlopen(upstream, timeout=600)
            except urllib.error.HTTPError as e:
                body = e.read()
                if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                    delay = min(60, 5 * 2 ** attempt)
                    print(f"[proxy] {e.code}, retry in {delay}s", flush=True)
                    time.sleep(delay)
                    continue
                _stats["errors"] += 1
                print(f"[proxy] HTTP {e.code}: {body[:300]!r}", flush=True)
                return self._send(e.code, body, "application/json")
            except Exception as e:  # network errors
                if attempt < MAX_RETRIES - 1:
                    time.sleep(5)
                    continue
                _stats["errors"] += 1
                return self._send(502, json.dumps({"error": str(e)}).encode(), "application/json")
            break

        _stats["requests"] += 1
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in iter(lambda: resp.read(4096), b""):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        else:
            body = resp.read()
            try:
                usage = json.loads(body).get("usage") or {}
                _stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
                _stats["completion_tokens"] += usage.get("completion_tokens", 0)
            except Exception:
                pass
            self._send(200, body, "application/json")
        if _stats["requests"] % 10 == 0:
            print(f"[proxy] {_stats}", flush=True)

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    Handler.key = load_key()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[proxy] listening on http://127.0.0.1:{args.port}/v1 -> {UPSTREAM} ({UPSTREAM_MODEL})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
