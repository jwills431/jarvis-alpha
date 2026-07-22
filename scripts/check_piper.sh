#!/bin/sh
# Verify a local Piper installation before selecting it as the JARVIS speech
# engine. Checks provisioning, renders a phrase, measures time-to-first-audio,
# and reports whether the latency is workable for a spoken assistant.
#
# Reads configuration but changes nothing. Plays audio only with --play.
# Usage: scripts/check_piper.sh [--play]
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$ROOT"

PLAY=0
[ "${1:-}" = "--play" ] && PLAY=1

CONFIG=${JARVIS_CONFIG:-config.local.json}
FAILED=0

read_config() {
  # $1 = key, $2 = fallback. Configuration is optional at this stage.
  [ -f "$CONFIG" ] || { printf '%s' "$2"; return; }
  python3 -c '
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        print(json.load(handle).get(sys.argv[2], sys.argv[3]))
except Exception:
    print(sys.argv[3])
' "$CONFIG" "$1" "$2"
}

ok()   { printf '  ok    %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; FAILED=$((FAILED + 1)); }
note() { printf '        %s\n' "$1"; }

PIPER_PYTHON=$(read_config piper_python "runtime/piper-venv/bin/python3")
VOICE=$(read_config piper_voice "models/piper/en_GB-alan-medium.onnx")
RATE=$(read_config tts_rate 190)
ENGINE=$(read_config tts_engine "say")
HELPER=scripts/piper_synthesize.py

echo "Piper provisioning check"
echo

# --- 1. Provisioning -------------------------------------------------------
if [ -x "$PIPER_PYTHON" ]; then
  ok "virtual environment interpreter is present: $PIPER_PYTHON"
else
  bad "virtual environment interpreter is missing: $PIPER_PYTHON"
  note "install it with: scripts/setup_piper.sh"
fi

if [ -x "$PIPER_PYTHON" ] && "$PIPER_PYTHON" -c 'import piper' 2>/dev/null; then
  ok "piper-tts imports successfully"
elif [ -x "$PIPER_PYTHON" ]; then
  bad "piper-tts is not importable in that environment"
  note "reinstall with: scripts/setup_piper.sh --force"
fi

if [ -f "$HELPER" ]; then
  ok "synthesis helper is present: $HELPER"
else
  bad "synthesis helper is missing: $HELPER"
fi

if [ -f "$VOICE" ]; then
  ok "voice model is present: $VOICE"
else
  bad "voice model is missing: $VOICE"
fi

# Piper loads its config from beside the model; a missing sidecar is the most
# common silent failure.
if [ -f "$VOICE.json" ]; then
  ok "voice config is present: $VOICE.json"
else
  bad "voice config is missing: $VOICE.json"
  note "the .onnx.json sidecar must sit alongside the .onnx model"
fi

for tool in /usr/bin/afplay /usr/bin/say; do
  if [ -x "$tool" ]; then ok "$tool is available"; else bad "$tool is unavailable"; fi
done

if [ "$FAILED" -ne 0 ]; then
  echo
  echo "Provisioning incomplete: $FAILED check(s) failed. Synthesis was not attempted."
  exit 1
fi

# --- 2. Render and time ----------------------------------------------------
echo
echo "Synthesis and latency"
echo

WAV=$(mktemp "${TMPDIR:-/tmp}/jarvis-piper-check.XXXXXX")
trap 'rm -f "$WAV" "$WAV.wav"' EXIT INT TERM HUP
WAV="$WAV.wav"

# A representative first phrase, not a single word: JARVIS speaks at sentence
# boundaries, so the first spoken unit is what the user actually waits for.
PHRASE='At your service. All systems are nominal and the local model is responding normally.'
LENGTH_SCALE=$(python3 -c "print(round(max(0.5, min(2.0, 190 / $RATE)), 3))")

START=$(python3 -c 'import time; print(time.time())')
# Exactly how JARVIS invokes it: text on standard input, never in arguments.
if ! printf '%s' "$PHRASE" | "$PIPER_PYTHON" "$HELPER" --model "$VOICE" \
     --output-file "$WAV" --length-scale "$LENGTH_SCALE" >/dev/null 2>/tmp/jarvis-piper-check.err; then
  bad "synthesis failed"
  note "stderr: $(head -3 /tmp/jarvis-piper-check.err 2>/dev/null || echo unavailable)"
  exit 1
fi
END=$(python3 -c 'import time; print(time.time())')

if [ ! -s "$WAV" ]; then
  bad "synthesis produced no audio"
  exit 1
fi

ELAPSED=$(python3 -c "print(round($END - $START, 2))")
AUDIO=$(python3 -c "
import wave
with wave.open('$WAV') as w:
    print(round(w.getnframes() / w.getframerate(), 2))
")
RATIO=$(python3 -c "print(round($ELAPSED / $AUDIO, 2) if $AUDIO else 0)")

ok "rendered ${AUDIO}s of audio in ${ELAPSED}s (length_scale $LENGTH_SCALE at $RATE WPM)"
note "real-time factor: ${RATIO}x  (below 1.0 renders faster than it plays)"
echo

# JARVIS renders each phrase fully before playing it, so this render time is
# dead air the user waits through at the start of every spoken phrase.
python3 - "$ELAPSED" "$RATIO" <<'PY'
import sys
elapsed, ratio = float(sys.argv[1]), float(sys.argv[2])
if elapsed <= 1.0:
    verdict = "Good: the pause before each phrase should feel natural."
elif elapsed <= 2.5:
    verdict = "Acceptable: a noticeable but tolerable pause before each phrase."
else:
    verdict = "Slow: this pause precedes every phrase and will feel laggy in conversation."
print(f"  Verdict: {verdict}")
if ratio >= 1.0:
    print("  Warning: rendering is slower than playback. Speech will fall behind")
    print("           generation on long replies. Consider a 'low' quality voice.")
PY

if [ "$PLAY" -eq 1 ]; then
  echo
  echo "Playing the rendered phrase; judge naturalness and pronunciation."
  /usr/bin/afplay "$WAV"
fi

echo
if [ "$ENGINE" = "piper" ]; then
  echo "tts_engine is already \"piper\". Restart JARVIS to apply configuration changes."
else
  echo "tts_engine is currently \"$ENGINE\". Set \"tts_engine\": \"piper\" in $CONFIG"
  echo "and restart to use this voice. See docs/PIPER_ACCEPTANCE.md for the"
  echo "on-device checklist."
fi
