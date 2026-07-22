#!/bin/sh
# Install the optional local Piper speech engine into an isolated virtual
# environment, and download a voice.
#
# Uses piper-tts (OHF-Voice/piper1-gpl), which ships its own libraries as a
# Python wheel. The older standalone macOS tarball from the archived
# rhasspy/piper repository is not usable: it omits the libraries its binary
# links against (upstream issue 404).
#
# Downloads only; changes no configuration and starts no service. Everything
# lands in the ignored runtime/ and models/ directories, so removing those two
# folders fully undoes this script.
#
# Usage: scripts/setup_piper.sh [medium|low] [--force]
#   medium (default) - better quality, slower to render
#   low              - faster to render, use if medium is too slow on this Mac
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$ROOT"

FORCE=0
QUALITY=medium
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    medium|low) QUALITY=$arg ;;
    *) echo "Usage: scripts/setup_piper.sh [medium|low] [--force]" >&2; exit 2 ;;
  esac
done

VENV=runtime/piper-venv
VOICE_NAME="en_GB-alan-$QUALITY"

echo "Piper setup ($QUALITY quality)"
echo

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script targets macOS." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Apple's command line tools first." >&2
  exit 1
fi

if [ "$FORCE" -eq 1 ]; then
  echo "Reinstalling: removing $VENV"
  rm -rf "$VENV"
fi

mkdir -p models/piper runtime

# --- Virtual environment ---------------------------------------------------
# Isolated so piper-tts and its dependencies never touch the system Python.
if [ ! -x "$VENV/bin/python3" ]; then
  echo "Creating the virtual environment..."
  python3 -m venv "$VENV"
fi

echo "Installing piper-tts..."
if ! "$VENV/bin/python3" -m pip install --quiet --upgrade pip; then
  echo "Could not upgrade pip inside the virtual environment." >&2
  exit 1
fi
if ! "$VENV/bin/python3" -m pip install --quiet piper-tts; then
  echo >&2
  echo "Installing piper-tts failed. If this Mac has no prebuilt wheel for its" >&2
  echo "Python version, try creating the environment with a different python3." >&2
  exit 1
fi

# Confirm the package imports before claiming success; a wheel can install and
# still fail to load if its bundled libraries do not match this machine.
if ! "$VENV/bin/python3" -c 'import piper' 2>/dev/null; then
  echo >&2
  echo "piper-tts installed but cannot be imported on this Mac." >&2
  "$VENV/bin/python3" -c 'import piper' || true
  exit 1
fi
echo "  installed piper-tts into $VENV"

# --- Voice -----------------------------------------------------------------
if [ -f "models/piper/$VOICE_NAME.onnx" ] && [ -f "models/piper/$VOICE_NAME.onnx.json" ]; then
  echo "  voice already present: models/piper/$VOICE_NAME.onnx"
else
  echo "Downloading the $VOICE_NAME voice..."
  if ! "$VENV/bin/python3" -m piper.download_voices "$VOICE_NAME" --data-dir models/piper; then
    echo >&2
    echo "Voice download failed. List available voices with:" >&2
    echo "  $VENV/bin/python3 -m piper.download_voices" >&2
    exit 1
  fi
fi

# Both files are required; Piper loads the config from beside the model.
for suffix in .onnx .onnx.json; do
  if [ ! -s "models/piper/$VOICE_NAME$suffix" ]; then
    echo "Expected file is missing after download: models/piper/$VOICE_NAME$suffix" >&2
    exit 1
  fi
done

echo
echo "Done. Installed:"
echo "  $VENV  (piper-tts)"
echo "  models/piper/$VOICE_NAME.onnx"
echo "  models/piper/$VOICE_NAME.onnx.json"
echo
if [ "$QUALITY" != "medium" ]; then
  echo "Set \"piper_voice\": \"models/piper/$VOICE_NAME.onnx\" in config.local.json"
  echo "to use this voice instead of the medium one."
  echo
fi
echo "Next step, which changes nothing and plays a sample:"
echo "  scripts/check_piper.sh --play"
