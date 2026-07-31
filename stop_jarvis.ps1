# stop_jarvis.ps1 - cleanly stop the JARVIS stack (app + llama.cpp + whisper + Fish)
# running in WSL. Run from a PowerShell prompt:  .\stop_jarvis.ps1
# (or right-click -> Run with PowerShell). Elevation is NOT required: the
# services run in WSL as your own user.

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

if ($result -match '__ALL_STOPPED__') {
  Write-Host "JARVIS stopped cleanly. App, model, recognizer and voice are all down." -ForegroundColor Green
} else {
  Write-Host "Some processes are still running:" -ForegroundColor Yellow
  $result | ForEach-Object { Write-Host "  $_" }
  Write-Host "Re-run this script, or use: wsl --shutdown" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "WSL itself is still running. To release its memory too:  wsl --shutdown" -ForegroundColor DarkGray
Write-Host "That is worth doing before shutting the machine down for the night." -ForegroundColor DarkGray
