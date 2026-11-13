# Reference eval (public Budget-Fit agent, verracodeguacas, Apache 2.0) on Kaggle GPUs: 30 competition tasks (eval30 set) + 30 mined tasks from other repos, same vLLM/harness as scoring.
# Agent = attached dataset with agent.yaml (sujithkamme/gemma4-agent-ref-budgetfit). Mined tasks come from the gemma4-task-miner output.
# Based on ryanholbrook/getting-started-gemma-4-developer-agent (Kaggle staff starter).
# Outputs (results, traces, patches, summary) land in /kaggle/working/results_<source>.

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
COMP_IDS = ["fastapi_13920", "fastapi_14077", "fastapi_14258", "fastapi_14419", "fastapi_14448", "fastapi_14458", "fastapi_14616", "fastapi_14794", "fastapi_14873", "fastapi_15588", "fastapi_15800", "fastapi_5077", "fastapi_9555", "fastapi_9753", "requests_6644", "rich_3006", "rich_3052", "rich_3105", "rich_3180", "rich_3470", "rich_3480", "rich_3521", "rich_3676", "rich_3772", "rich_3777", "rich_3782", "rich_3930", "rich_3934", "rich_3935", "rich_4079"]
# 2 per repo + random fill from kaggle/mined_solvable.json (random.Random(0)).
MINED_IDS = ["arrow_1200", "arrow_1201", "boltons_343", "boltons_451", "jsonschema_1224", "jsonschema_1416", "more_itertools_1127", "more_itertools_1154", "more_itertools_1253", "parso_234", "parso_237", "pyflakes_729", "pyflakes_745", "pyflakes_868", "pygments_2270", "pygments_3078", "python_tabulate_125", "python_tabulate_366", "sqlparse_332", "sqlparse_633", "tenacity_479", "tenacity_615", "tenacity_629", "tenacity_654", "tomlkit_527", "tomlkit_567", "toolz_603", "toolz_635", "typer_1788", "typer_1791"]
# Same budget as the agent's eval_config.yaml (8 min, 28 calls, 240 s).
EVAL_CONFIG = {'timeout_seconds': 240, 'verification_timeout_seconds': 300, 'max_tool_calls': 28,
               'max_time_minutes': 8, 'max_turns': 80}
STOP_AFTER_MINUTES = 600                 # GPU quota guard: start no new task after this

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

# ---------------------------------------------------------------- 4. mined tasks' dependency wheels
MINED = Path(glob.glob('/kaggle/input/**/mined/tasks.jsonl', recursive=True)[0]).parent


def install_mined_wheels():
    # Run after vLLM is up and after the competition tasks, so neither sees these packages.
    # Skips packages the harness ships.
    harness_pkgs = {w.name.split('-')[0].lower().replace('_', '-') for w in WHEELHOUSE_DIR.glob('*.whl')}
    extra = {}
    for w in sorted(MINED.glob('wheels/*/*.whl')):
        pkg = w.name.split('-')[0].lower().replace('_', '-')
        if pkg not in harness_pkgs:
            extra[pkg] = str(w)          # one version per package (last repo wins)
    log(f'installing {len(extra)} mined dependency wheels')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *extra.values()])


# ---------------------------------------------------------------- 5. evaluate
limits, gen_constraints = build_submission_limits()
EMPTY = WORK / 'empty'
EMPTY.mkdir(parents=True, exist_ok=True)
# Mined tasks have no code graphs/embeddings, so graph/embedding tools return nothing there.
SOURCES = [
    ('comp', DATA_DIR, COMP_IDS, DATA_DIR / 'graphs', DATA_DIR / 'embeddings'),
    ('mined', MINED, MINED_IDS, EMPTY, EMPTY),
]
rows = []
for source, data, ids, graphs, embeddings in SOURCES:
    if source == 'mined':
        install_mined_wheels()
    tasks = [t for t in load_tasks(data / 'tasks.jsonl') if t.instance_id in ids]
    evaluator = Evaluator(EvalConfig(
        tasks_path=data / 'tasks.jsonl', snapshots_dir=data / 'snapshots', results_dir=WORK / f'results_{source}',
        submission_dir=AGENT_DIR, models=models, sandbox='subprocess',
        timeout_seconds=EVAL_CONFIG['timeout_seconds'],
        verification_timeout_seconds=EVAL_CONFIG['verification_timeout_seconds'],
        max_time_minutes=EVAL_CONFIG['max_time_minutes'], max_tool_calls=EVAL_CONFIG['max_tool_calls'],
        max_turns=EVAL_CONFIG['max_turns'], limits=limits, generation_constraints=gen_constraints,
        adapter_manifest=adapters,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2,
                                                        token_threshold=14336, event_retention_size=5),
        graph_dir=str(graphs), embeddings_dir=str(embeddings),
        wheels_dir=data / 'wheels', verbose=False,
    ))
    for i, task in enumerate(tasks, 1):
        if (time.time() - T0) / 60 > STOP_AFTER_MINUTES:
            log(f'quota guard: stopping before {source} task {i}')
            break
        log(f'[{source} {i}/{len(tasks)}] {task.instance_id}')
        try:
            r = asyncio.run(evaluator.evaluate_task(task=task, task_index=i, total_tasks=len(tasks)))
            row = {'source': source, 'id': task.instance_id, 'resolved': bool(r.resolved),
                   'exit_code': r.test_exit_code, 'tool_calls': r.tool_calls,
                   'seconds': round(r.duration_seconds, 1), 'patch_chars': len((r.agent_patch or '').strip()),
                   'error': getattr(r, 'error', None) or getattr(r, 'error_message', None)}
        except Exception as e:  # keep going; record the failure
            row = {'source': source, 'id': task.instance_id, 'resolved': False, 'error': f'{type(e).__name__}: {e}'}
        rows.append(row)
        log(f'    -> {row}')
        (WORK / 'eval_rows.json').write_text(json.dumps(rows, indent=2))

by_source = {}
for source, *_ in SOURCES:
    rs = [r for r in rows if r['source'] == source]
    by_source[source] = {'resolved': sum(r['resolved'] for r in rs), 'total': len(rs)}
summary = {'model': declared_model, 'eval_config': EVAL_CONFIG, 'by_source': by_source,
           'minutes': round((time.time() - T0) / 60, 1), 'rows': rows}
(WORK / 'eval_summary.json').write_text(json.dumps(summary, indent=2))
log(f'DONE {by_source}')
server.stop()
