# stop_jarvis.ps1 - cleanly stop the JARVIS stack (app + llama.cpp + Fish) running in WSL.
# Run from a PowerShell prompt:  .\stop_jarvis.ps1
# (or right-click -> Run with PowerShell)

Write-Host "Stopping JARVIS stack..." -ForegroundColor Cyan

# Process command-line patterns for the three services.
$patterns = @('jarvis.server', 'llama-server', 'tools.api_server')

# 1) Ask each to exit gracefully (SIGTERM). This lets the app release the Piper
#    worker and close sockets cleanly.
foreach ($p in $patterns) {
  wsl -d Ubuntu bash -lc "pkill -TERM -f '$p' 2>/dev/null; true" | Out-Null
}

Start-Sleep -Seconds 3

# 2) Force-kill anything that ignored the graceful stop.
foreach ($p in $patterns) {
  wsl -d Ubuntu bash -lc "pkill -KILL -f '$p' 2>/dev/null; true" | Out-Null
}

Start-Sleep -Seconds 1

# 3) Confirm the app port is down.
$health = wsl -d Ubuntu bash -lc "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/api/health 2>/dev/null"
if ([string]::IsNullOrWhiteSpace($health) -or $health -eq '000') {
  Write-Host "JARVIS stopped cleanly. All three services are down." -ForegroundColor Green
} else {
  Write-Host "Warning: the app still responded (HTTP $health). Re-run this script or check WSL." -ForegroundColor Yellow
}

Write-Host "(WSL itself is left running. To stop the whole WSL VM too, run:  wsl --shutdown )" -ForegroundColor DarkGray
