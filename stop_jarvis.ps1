# stop_jarvis.ps1 - cleanly stop the JARVIS stack (app + llama.cpp + whisper + Fish)
# running in WSL. Elevation is NOT required: the services run in WSL as your user.
#
#   .\stop_jarvis.ps1              stop the services, leave WSL running (fast restart)
#   .\stop_jarvis.ps1 -Shutdown    stop the services AND shut WSL down (release memory)
#   .\stop_jarvis.ps1 -KeepWsl     same as the default; kept for compatibility
#
# A plain stop leaves the WSL VM up, so a following start_jarvis is quick and Fish
# does not have to pay its ~2-minute warmup again. Shutting WSL down releases the
# VM's memory (worth doing before the machine goes off for the night) but kills
# EVERY WSL distro and anything running inside them, so it is opt-in via -Shutdown.

param(
  [switch]$KeepWsl,
  [switch]$Shutdown
)

Write-Host "Stopping JARVIS stack..." -ForegroundColor Cyan

# Patterns are bracketed - "[j]arvis.server" instead of "jarvis.server" - so the
# regex cannot match the command line of the very shell running pkill. Without
# that, pkill killed its own parent shell mid-run and the script appeared to hang
# after printing this first line.
$patterns = @('[j]arvis.server', '[l]lama-server', '[w]hisper-server', '[t]ools.api_server')
$joined = $patterns -join '|'

# One call does the whole sequence, so a killed shell cannot strand the rest:
# ask politely, wait, then insist.
$script = @"
pkill -TERM -f '$joined' 2>/dev/null
sleep 3
pkill -KILL -f '$joined' 2>/dev/null
sleep 1
pgrep -af '$joined' || echo __ALL_STOPPED__
"@

$result = $script | wsl -d Ubuntu bash 2>&1
$stopped = $result -match '__ALL_STOPPED__'

if ($stopped) {
  Write-Host "JARVIS stopped. App, model, recognizer and voice are all down." -ForegroundColor Green
} else {
  Write-Host "Some processes are still running:" -ForegroundColor Yellow
  $result | ForEach-Object { Write-Host "  $_" }
  Write-Host "Re-run this script, or use: wsl --shutdown" -ForegroundColor Yellow
}

# WSL is left running by default so a following start_jarvis is fast. Only tear
# the VM down when -Shutdown is passed. -KeepWsl is accepted for compatibility
# and is now the default, so it takes precedence over nothing to do.
if (-not $Shutdown) {
  Write-Host "`nWSL left running. Restart quickly with .\start_jarvis.ps1 (add -Tools for the tool loop)." -ForegroundColor DarkGray
  Write-Host "To release the VM's memory (e.g. overnight), re-run with -Shutdown." -ForegroundColor DarkGray
  return
}

Write-Host "`nShutting down WSL (this can take up to a minute)..." -ForegroundColor Cyan
wsl --shutdown
Start-Sleep -Seconds 2
Write-Host "WSL shut down. Memory released; safe to power off." -ForegroundColor Green
