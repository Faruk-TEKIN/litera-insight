#!/bin/sh
set -eu

MODEL_NAME="${MODEL_NAME:-qwen2.5:0.5b}"

until ollama list >/dev/null 2>&1; do
  sleep 2
done

echo "Pulling Ollama model: ${MODEL_NAME}"
ollama pull "${MODEL_NAME}"
