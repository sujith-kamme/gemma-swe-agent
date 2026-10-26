# 30-task eval on Kaggle GPUs (agent = attached dataset with agent.yaml, else sample_submission): official vLLM + swegemma harness, same setup as scoring.
# Based on ryanholbrook/getting-started-gemma-4-developer-agent (Kaggle staff starter).
# Outputs (results, traces, patches, summary) land in /kaggle/working/results.

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- config
MODEL_NAME = os.environ.get('MODEL_NAME', 'gemma-4-31b-it-qat-w4a16-ct')
KEEP_SAMPLE_ADAPTERS = False  # sample adapters are dummies; baseline = plain base model
TASK_IDS = ["fastapi_14794", "rich_3006", "rich_3777", "fastapi_9555", "rich_3470", "fastapi_15588", "rich_3521", "rich_3935", "rich_3480"]
# Budget we would actually submit (written into the agent's eval_config.yaml).
EVAL_CONFIG = {
    'timeout_seconds': 90,               # per-command timeout (not per task)
    'verification_timeout_seconds': 300,
    'max_tool_calls': 50,
    'max_time_minutes': 5,
    'max_turns': 100,
}
STOP_AFTER_MINUTES = 55                  # GPU quota guard: start no new task after this

os.environ.update({
    'TRANSFORMERS_NO_TF': '1', 'TRANSFORMERS_NO_FLAX': '1', 'TRANSFORMERS_OFFLINE': '1',
    'VLLM_NO_USAGE_STATS': '1', 'VLLM_WORKER_MULTIPROC_METHOD': 'spawn',
    'VLLM_ENGINE_READY_TIMEOUT_S': '1200', 'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS': '1',
    'NCCL_DEBUG': 'WARN', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'LITELLM_TELEMETRY': 'False',
    'LITELLM_LOG': 'WARNING', 'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True',
    'OTEL_SDK_DISABLED': 'true', 'OTEL_PYTHON_DISABLED': 'true',
})
os.environ.setdefault('OPENAI_API_KEY', 'EMPTY')
os.environ.setdefault('LOCAL_API_KEY', 'EMPTY')

T0 = time.time()


def log(msg):
    print(f'[{(time.time() - T0) / 60:6.1f}m] {msg}', flush=True)


# ---------------------------------------------------------------- 1. install wheelhouse
def find_input(*candidates):
    for c in candidates:
        hits = glob.glob(c)
        if hits:
            return Path(hits[0])
    raise FileNotFoundError(candidates)


WHEELHOUSE_DIR = find_input('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse',
                            '/kaggle/input/gemma-4-developer-agent-wheelhouse')
for pth in glob.glob('/usr/local/lib/python*/*-packages/*cutlass*.pth'):
    try:
        os.unlink(pth)
    except OSError:
        pass
tmp_whl = Path('/tmp/wheelhouse')
tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower():
        continue
    name = w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name
    if not (tmp_whl / name).exists():
        os.symlink(w, tmp_whl / name)
wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))
log(f'installing {len(wheels)} wheels')
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels],
               check=True)

import asyncio  # noqa: E402
import litellm  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402
from adk_submission import VllmConfig, VllmServer, discover_adapters  # noqa: E402
from adk_submission.discovery import discover_declared_models  # noqa: E402
from google.adk.agents.context_cache_config import ContextCacheConfig  # noqa: E402
from google.adk.apps._configs import EventsCompactionConfig  # noqa: E402
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS, EvalConfig, build_submission_limits  # noqa: E402
from swegemma.evaluate import Evaluator  # noqa: E402
from swegemma.models import load_tasks  # noqa: E402

litellm.drop_params = True
log(f'GPUs: {torch.cuda.device_count()} x {torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none"}')

# ---------------------------------------------------------------- 2. agent dir
DATA_DIR = find_input('/kaggle/input/competitions/gemma-4-developer-agent', '/kaggle/input/gemma-4-developer-agent')
WORK = Path('/kaggle/working')
AGENT_DIR = WORK / 'agent'
shutil.rmtree(AGENT_DIR, ignore_errors=True)
# Use our own agent if attached as a dataset (kaggle/agent), else the sample submission.
custom = glob.glob('/kaggle/input/**/agent.yaml', recursive=True)
custom = [Path(p).parent for p in custom if 'sample_submission' not in p]
shutil.copytree(custom[0] if custom else DATA_DIR / 'sample_submission', AGENT_DIR)
log(f'agent source: {custom[0] if custom else "sample_submission"}')

for y in [AGENT_DIR / 'agent.yaml', *sorted((AGENT_DIR / 'sub_agents').glob('*.yaml'))]:
    if y.is_file():
        text = re.sub(r'^(\s*model:\s*).*$', rf'\g<1>{MODEL_NAME}', y.read_text(), flags=re.M)
        if not KEEP_SAMPLE_ADAPTERS:
            text = re.sub(r'^\s*adapter:\s*.*\n?', '', text, flags=re.M)
        y.write_text(text)
if not KEEP_SAMPLE_ADAPTERS:
    shutil.rmtree(AGENT_DIR / 'adapters', ignore_errors=True)
(AGENT_DIR / 'eval_config.yaml').write_text(yaml.safe_dump({'evaluation': EVAL_CONFIG}))

# ---------------------------------------------------------------- 3. vLLM (scoring config)
declared = discover_declared_models(AGENT_DIR)
assert len(declared) == 1, declared
declared_model = next(iter(declared))
MODEL_PATH = find_input(f'/kaggle/input/models/google/gemma-4/other/{declared_model}/2',
                        f'/kaggle/input/gemma-4/other/{declared_model}/2',
                        f'/kaggle/input/**/{declared_model}/2')
adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
adapter_map = getattr(adapters, 'adapters', None) or {}
ranks = [r for i in adapter_map.values() if (r := getattr(i, 'rank', None))]
gpus = torch.cuda.device_count()
tp = 4 if gpus >= 4 else (2 if gpus >= 2 else 1)

server = VllmServer(VllmConfig(
    model=str(MODEL_PATH), port=8000, host='127.0.0.1',
    tool_call_parser='gemma4', reasoning_parser='gemma4', max_model_len=32768,
    dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto',
    gpu_memory_utilization=0.90, enable_auto_tool_choice=True,
    enable_lora=bool(adapter_map), max_loras=max(1, len(adapter_map)),
    max_lora_rank=max(ranks) if ranks else 128, scheduler_reserve_full_isl=False,
    tensor_parallel_size=tp, startup_timeout=60 * 20,
    extra_args=(('--hf-overrides', '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}')
                if declared_model == 'gemma-4-12b-it-qat-w4a16-ct' else ()),
), adapter_manifest=adapters)
log(f'starting vLLM {declared_model} tp={tp}')
server.start()
log(f'vLLM up at {server.base_url}')
models = server.create_model_registry(aliases=[declared_model], model_prefix='openai/',
                                      api_key=os.environ['LOCAL_API_KEY'])

# ---------------------------------------------------------------- 4. evaluate
tasks = [t for t in load_tasks(DATA_DIR / 'tasks.jsonl') if not TASK_IDS or t.instance_id in TASK_IDS]
limits, gen_constraints = build_submission_limits()
RESULTS = WORK / 'results'
evaluator = Evaluator(EvalConfig(
    tasks_path=DATA_DIR / 'tasks.jsonl', snapshots_dir=DATA_DIR / 'snapshots', results_dir=RESULTS,
    submission_dir=AGENT_DIR, models=models, sandbox='subprocess',
    timeout_seconds=EVAL_CONFIG['timeout_seconds'],
    verification_timeout_seconds=EVAL_CONFIG['verification_timeout_seconds'],
    max_time_minutes=EVAL_CONFIG['max_time_minutes'], max_tool_calls=EVAL_CONFIG['max_tool_calls'],
    max_turns=EVAL_CONFIG['max_turns'], limits=limits, generation_constraints=gen_constraints,
    adapter_manifest=adapters,
    context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
    events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2,
                                                    token_threshold=14336, event_retention_size=5),
    graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'),
    wheels_dir=DATA_DIR / 'wheels', verbose=False,
))

rows = []
for i, task in enumerate(tasks, 1):
    if (time.time() - T0) / 60 > STOP_AFTER_MINUTES:
        log(f'quota guard: stopping before task {i}')
        break
    log(f'[{i}/{len(tasks)}] {task.instance_id}')
    try:
        r = asyncio.run(evaluator.evaluate_task(task=task, task_index=i, total_tasks=len(tasks)))
        row = {'id': task.instance_id, 'resolved': bool(r.resolved), 'exit_code': r.test_exit_code,
               'tool_calls': r.tool_calls, 'seconds': round(r.duration_seconds, 1),
               'patch_chars': len((r.agent_patch or '').strip()),
               'error': getattr(r, 'error', None) or getattr(r, 'error_message', None)}
    except Exception as e:  # keep going; record the failure
        row = {'id': task.instance_id, 'resolved': False, 'error': f'{type(e).__name__}: {e}'}
    rows.append(row)
    log(f'    -> {row}')
    (WORK / 'baseline_rows.json').write_text(json.dumps(rows, indent=2))

solved = sum(r['resolved'] for r in rows)
summary = {'model': declared_model, 'eval_config': EVAL_CONFIG, 'resolved': solved, 'total': len(rows),
           'rate': solved / max(1, len(rows)), 'minutes': round((time.time() - T0) / 60, 1), 'rows': rows}
(WORK / 'baseline_summary.json').write_text(json.dumps(summary, indent=2))
log(f'DONE {solved}/{len(rows)} resolved')
server.stop()
