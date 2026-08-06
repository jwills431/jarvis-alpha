# restart_app.ps1 - restart ONLY the JARVIS web app (jarvis.server) in WSL,
# leaving llama.cpp, whisper-server, and Fish running untouched. Use this while
# iterating on app/tool code so you don't pay Fish's ~2-minute warmup each time.
#
#   .\restart_app.ps1
#
# (For a full stack bring-up use start_jarvis.ps1; to stop everything use
# stop_jarvis.ps1.) The app reads config.local.json and the Python source fresh
# on each start, so this picks up changes to jarvis/*.py and the config.

Write-Host "Restarting JARVIS app (llama / whisper / Fish left running)..." -ForegroundColor Cyan

# Piped into WSL over stdin to dodge quoting issues, same as start_jarvis.ps1.
# The launching shell is kept alive with a health-wait loop; without that, WSL
# reaps the detached child before it establishes.
$launcher = @'
set -u
PROJ="/mnt/d/Claude Projects/JARVIS AI Assistant"
cd "$PROJ" || exit 1

# Stop the current app only (bracketed pattern so pkill can't match this shell).
pkill -f '[j]arvis.server' 2>/dev/null
sleep 1

# Relaunch detached; setsid keeps it alive after this shell exits.
setsid bash -c 'cd "'"$PROJ"'"; python3 -m jarvis.server > /tmp/jarvis_app.log 2>&1' < /dev/null &

# Wait for it to answer. -k because the app serves self-signed TLS; no -f because
# a 401 (auth on) still means the server is up and responding. The final check
# uses the inline || idiom (not a multi-line if/fi) to stay robust when the
# script is piped into WSL, matching start_jarvis.ps1.
for i in $(seq 1 15); do
  sleep 1
  curl -sk https://127.0.0.1:8787/api/health > /dev/null 2>&1 && { echo "app ready (~${i}s)"; break; }
done
curl -sk https://127.0.0.1:8787/api/health > /dev/null 2>&1 || { echo "ERROR: app did not come up; last log lines:"; tail -12 /tmp/jarvis_app.log; exit 1; }
'@

# PowerShell re-adds CRLF when piping a string into a native process, and bash
# then chokes on the carriage returns ($'\r': command not found; unterminated
# brace groups). Sidestep line endings and quoting entirely: send the script as
# base64 and decode + run it inside the VM, so only clean LF bytes reach bash.
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($launcher.Replace("`r", "")))
wsl -d Ubuntu bash -lc "echo $encoded | base64 -d | bash"
if ($LASTEXITCODE -ne 0) {
  Write-Host "App restart failed - see the log tail above." -ForegroundColor Yellow
  return
}

Write-Host ""
Write-Host "App restarted. Open https://localhost:8787 (or the LAN address)." -ForegroundColor Green
