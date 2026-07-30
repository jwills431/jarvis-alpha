# start_jarvis.ps1 - bring up the full JARVIS stack (llama.cpp + app + Fish) in WSL.
# Run from a PowerShell prompt:  .\start_jarvis.ps1
# (pairs with stop_jarvis.ps1). llama + app come up in seconds; Fish then warms
# up for ~2 minutes (one-time torch.compile) before spoken replies work.

Write-Host "Starting JARVIS stack..." -ForegroundColor Cyan

# The whole launcher is a bash script piped into WSL over stdin, which avoids any
# Windows/WSL quoting pitfalls. Each service is detached with setsid so it keeps
# running after this script (and the launching shell) exits.
$launcher = @'
set -u
PROJ="/mnt/d/Claude Projects/JARVIS AI Assistant"
cd "$PROJ" || exit 1
export JARVIS_MODEL_PATH=/home/jaydubya/jarvis/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf
export JARVIS_LLAMA_SERVER=/home/jaydubya/jarvis/llama.cpp/build/bin/llama-server
export JARVIS_GPU_LAYERS=99

# Already running? Do nothing rather than double-launch.
if curl -sf http://127.0.0.1:8787/api/health > /dev/null 2>&1; then
  echo "JARVIS app already running."; exit 0
fi

# 1) LLM backend, then wait for it to load onto the GPU.
setsid bash -c './scripts/run_backend.sh > /tmp/jarvis_llama.log 2>&1' < /dev/null &
for i in $(seq 1 40); do
  sleep 2
  curl -sf http://127.0.0.1:8081/health > /dev/null 2>&1 && { echo "llama ready (~$((i*2))s)"; break; }
done
curl -sf http://127.0.0.1:8081/health > /dev/null 2>&1 || { echo "ERROR: llama did not start; see /tmp/jarvis_llama.log"; tail -8 /tmp/jarvis_llama.log; exit 1; }

# 2) The JARVIS app.
setsid bash -c 'cd "'"$PROJ"'"; python3 -m jarvis.server > /tmp/jarvis_app.log 2>&1' < /dev/null &
sleep 4
echo "app health: $(curl -s http://127.0.0.1:8787/api/health)"

# 3) Fish neural TTS. The trailing sleep lets the detached process establish
#    before this script exits, otherwise WSL reaps it.
setsid bash -c 'cd /home/jaydubya/jarvis/fish-speech; .venv/bin/python -m tools.api_server --listen 127.0.0.1:8080 --half --compile --llama-checkpoint-path checkpoints/openaudio-s1-mini --decoder-checkpoint-path checkpoints/openaudio-s1-mini/codec.pth --decoder-config-name modded_dac_vq > /tmp/jarvis_fish.log 2>&1' < /dev/null &
sleep 6
test -f /tmp/jarvis_fish.log && echo "fish launched (warming up ~2 min)" || echo "WARNING: fish log not created"
'@

$launcher | wsl -d Ubuntu bash -l

Write-Host ""
Write-Host "Open http://localhost:8787  (voice replies become available once Fish finishes warming up)." -ForegroundColor Green
Write-Host "Tip: watch Fish come online with:  wsl -d Ubuntu bash -lc 'curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8080/v1/health'" -ForegroundColor DarkGray
