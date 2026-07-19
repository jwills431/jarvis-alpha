#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
MODEL=${JARVIS_MODEL_PATH:-"$ROOT/models/qwen2.5-7b-instruct-q4_k_m.gguf"}
BENCH=${JARVIS_LLAMA_BENCH:-"$ROOT/runtime/llama.cpp/build/bin/llama-bench"}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$ROOT/benchmark/results/$STAMP"
mkdir -p "$OUT"
test -x "$BENCH" || { echo "llama-bench is not built: $BENCH" >&2; exit 1; }
test -f "$MODEL" || { echo "model is missing: $MODEL" >&2; exit 1; }
# Conservative batches are required for this Intel/AMD Metal path. The same
# geometry is used for both backends so the comparison remains controlled.
"$BENCH" --model "$MODEL" --threads 10 --n-gpu-layers 0 --n-prompt 64 --n-gen 16 --batch-size 256 --ubatch-size 64 --repetitions 3 --output json > "$OUT/cpu.json" 2> "$OUT/cpu.log"
"$BENCH" --model "$MODEL" --threads 10 --n-gpu-layers 99 --n-prompt 64 --n-gen 16 --batch-size 256 --ubatch-size 64 --repetitions 3 --output json > "$OUT/metal.json" 2> "$OUT/metal.log"
shasum -a 256 "$MODEL" > "$OUT/model.sha256"
"$ROOT/runtime/llama.cpp/build/bin/llama-server" --version > "$OUT/llama-version.txt" 2>&1
printf '%s\n' "$OUT"
