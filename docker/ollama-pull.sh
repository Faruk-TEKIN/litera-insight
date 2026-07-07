#!/bin/sh
set -eu

MODEL_NAME="${MODEL_NAME:-qwen2.5:0.5b}"
WORKER_MODEL_NAME="${WORKER_MODEL_NAME:-}"

until ollama list >/dev/null 2>&1; do
  sleep 2
done

echo "Pulling Ollama model: ${MODEL_NAME}"
ollama pull "${MODEL_NAME}"

echo "Warming Ollama model: ${MODEL_NAME}"
ollama run "${MODEL_NAME}" "warmup" >/dev/null 2>&1 || true

# Worker için farklı bir model tanımlanmışsa onu da indir
if [ -n "${WORKER_MODEL_NAME}" ] && [ "${WORKER_MODEL_NAME}" != "${MODEL_NAME}" ]; then
  echo "Pulling worker Ollama model: ${WORKER_MODEL_NAME}"
  ollama pull "${WORKER_MODEL_NAME}"
  echo "Warming worker Ollama model: ${WORKER_MODEL_NAME}"
  ollama run "${WORKER_MODEL_NAME}" "warmup" >/dev/null 2>&1 || true
fi
