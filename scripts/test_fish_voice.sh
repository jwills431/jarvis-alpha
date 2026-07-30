#!/usr/bin/env bash
# Quick end-to-end test of the JARVIS Fish (neural) voice.
#
# Run this INSIDE WSL/Ubuntu on the server (GUItech-CORE):
#
#   bash "/mnt/d/Claude Projects/JARVIS AI Assistant/scripts/test_fish_voice.sh"
#   bash "/mnt/d/Claude Projects/JARVIS AI Assistant/scripts/test_fish_voice.sh" "Any line you want JARVIS to say."
#
# It starts the Fish server if it isn't already running, synthesizes the text in
# the cloned JARVIS voice, and saves a WAV into your project folder so you can
# open it from Windows and listen.
set -euo pipefail

FISH_DIR="$HOME/jarvis/fish-speech"
URL="http://127.0.0.1:8080"
OUT="/mnt/d/Claude Projects/JARVIS AI Assistant/jarvis_voice_out.wav"
TEXT="${1:-Good evening, sir. All systems are online and functioning within normal parameters.}"

# 1. Start the resident Fish server if it isn't already up.
if ! curl -sf "$URL/v1/health" >/dev/null 2>&1; then
  echo "Fish server not running - starting it (first run compiles, ~1-2 min)..."
  cd "$FISH_DIR"
  nohup .venv/bin/python -m tools.api_server \
    --listen 127.0.0.1:8080 --half --compile \
    --llama-checkpoint-path checkpoints/openaudio-s1-mini \
    --decoder-checkpoint-path checkpoints/openaudio-s1-mini/codec.pth \
    --decoder-config-name modded_dac_vq > /tmp/fish_srv.log 2>&1 &
  echo -n "Waiting for the model to load"
  for _ in $(seq 1 120); do
    curl -sf "$URL/v1/health" >/dev/null 2>&1 && break
    echo -n "."; sleep 2
  done
  echo
fi
curl -sf "$URL/v1/health" >/dev/null 2>&1 || { echo "Server did not come up - see /tmp/fish_srv.log"; exit 1; }

# 2. Synthesize the text in the cloned JARVIS voice (stdlib only, no quoting traps).
echo "Synthesizing: $TEXT"
python3 - "$TEXT" "$OUT" <<'PY'
import json, sys, urllib.request
text, out = sys.argv[1], sys.argv[2]
body = json.dumps({
    "text": text, "reference_id": "jarvis", "format": "wav",
    "temperature": 0.7, "top_p": 0.7, "repetition_penalty": 1.2,
    "use_memory_cache": "on",
}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/tts", data=body,
    headers={"Content-Type": "application/json"}, method="POST",
)
audio = urllib.request.urlopen(req, timeout=180).read()
assert audio[:4] == b"RIFF", "server did not return audio"
open(out, "wb").write(audio)
print(f"Saved {len(audio)} bytes")
PY

echo
echo "Done. Open this file to listen:"
echo '  D:\Claude Projects\JARVIS AI Assistant\jarvis_voice_out.wav'
