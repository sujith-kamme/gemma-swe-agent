"""Probe an OpenAI-compatible endpoint for Gemma 4 tool calling."""
import json, os, sys, time, urllib.request

def load_env(path=".env"):
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

ENDPOINTS = {
    "nim": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "google/gemma-4-31b-it"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "google/gemma-4-31b-it:free"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemma-4-31b-it"),
}

TOOLS = [{"type": "function", "function": {
    "name": "read_file", "description": "Read a file from the repo.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]

def probe(name):
    base, keyvar, model = ENDPOINTS[name]
    body = {"model": model, "temperature": 0.2, "max_tokens": 512, "tools": TOOLS,
            "messages": [{"role": "user", "content": "Read the file src/app.py using the tool."}]}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + os.environ[keyvar], "Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"[{name}] HTTP {e.code}: {e.read().decode()[:400]}"); return
    except Exception as e:
        print(f"[{name}] error: {e}"); return
    msg = out["choices"][0]["message"]
    print(f"[{name}] {time.time()-t:.1f}s finish={out['choices'][0].get('finish_reason')}")
    print(f"  tool_calls={json.dumps(msg.get('tool_calls'))[:300]}")
    print(f"  content={str(msg.get('content'))[:200]!r}")

if __name__ == "__main__":
    load_env()
    for n in sys.argv[1:] or ENDPOINTS:
        probe(n)
