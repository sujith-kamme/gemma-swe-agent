# gemma-swe-agent

An agent for the Kaggle [Gemma 4 Developer Agent](https://www.kaggle.com/competitions/gemma-4-developer-agent) competition. It is a declarative Google ADK config that runs Gemma 4 inside the official `swegemma` harness to fix real GitHub issues.

## Layout

| Path | What |
|---|---|
| `agents/v1/` | Submission directory (`agent.yaml`, prompts, sampling config, eval budget) |
| `kaggle/baseline/` | Kaggle GPU notebook: official vLLM setup plus the harness, run on a task subset |
| `kaggle/v1run/` | The same notebook, run on the `agents/v1` dataset |
| `kaggle/goldcheck/` | CPU notebook that runs every task with its gold patch to find which tasks are solvable |
| `scripts/gold_check.py` | Local gold-patch check (Docker or subprocess sandbox) |
| `scripts/test_endpoint.py` | Probe for tool calling on hosted Gemma 4 endpoints |
| `local_eval/` | Local Mac loop: harness plus Docker sandbox plus a hosted model through `gemini_proxy.py` |

## Setup

Competition data, harness wheels and model weights are not in this repo. Download them from Kaggle:

```bash
uv venv --python 3.12 && uv pip install --python .venv/bin/python kaggle
kaggle competitions download gemma-4-developer-agent              # dataset
kaggle datasets download metric/gemma-4-developer-agent-wheelhouse \
  -f swegemma-0.2.11-py3-none-any.whl                              # plus adk_submission, adk_eval_core
uv pip install --python .venv/bin/python wheelhouse/*.whl google-adk==1.36.1 google-genai==2.11.0 litellm==1.83.14
```

Put API keys in `.env` (git-ignored). Put the Kaggle token in `.kaggle/access_token` and pass it with `KAGGLE_API_TOKEN=$(cat .kaggle/access_token)`.

## Results (10-task subset, gemma-4-31b-it-qat-w4a16-ct, Kaggle 4x L4)

| Agent | Resolved |
|---|---|
| sample_submission (no adapters) | 4/10 |
| v1 | pending |

## License

MIT
