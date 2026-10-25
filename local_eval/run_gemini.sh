#!/usr/bin/env bash
# Usage: local_eval/run_gemini.sh <results_name> <task_id>[,<task_id>...] [extra swegemma args]
set -euo pipefail
# Requires: .venv/bin/python local_eval/gemini_proxy.py running (strips vLLM-only params).
cd "$(dirname "$0")/.."
: "${PROXY_URL:=http://127.0.0.1:8787/v1}"
export OPENAI_API_KEY=local-proxy
export OPENAI_BASE_URL="$PROXY_URL"
name=$1; ids=$2; shift 2
DATA=gemma-4-developer-agent
exec .venv/bin/swegemma eval \
  --tasks $DATA/tasks.jsonl \
  --snapshots-dir $DATA/snapshots \
  --results-dir local_eval/results/$name \
  --submission-dir ${SUBMISSION:-$DATA/sample_submission} \
  --models-yaml local_eval/models_gemini.yaml \
  --task-ids ${ids//,/ } \
  "$@"
