#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
MODEL=${JARVIS_MODEL_PATH:-"$ROOT/models/qwen2.5-7b-instruct-q4_k_m.gguf"}
SERVER=${JARVIS_LLAMA_SERVER:-"$ROOT/runtime/llama.cpp/build/bin/llama-server"}
GPU_LAYERS=${JARVIS_GPU_LAYERS:-0}
CACHE_REUSE=${JARVIS_CACHE_REUSE:-64}
KEY_FILE="$ROOT/.runtime-api-key"
test -x "$SERVER" || { echo "llama-server is not built: $SERVER" >&2; exit 1; }
test -f "$MODEL" || { echo "model is missing: $MODEL" >&2; exit 1; }
if [ ! -f "$KEY_FILE" ]; then
  umask 077
  openssl rand -hex 32 > "$KEY_FILE"
fi
exec "$SERVER" --model "$MODEL" --host 127.0.0.1 --port 8081 --ctx-size 4096 --parallel 1 --threads 10 --n-gpu-layers "$GPU_LAYERS" --cache-reuse "$CACHE_REUSE" --no-webui --api-key-file "$KEY_FILE" --cors-origins http://127.0.0.1:8787
