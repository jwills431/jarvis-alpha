# stop_jarvis.ps1 - cleanly stop the JARVIS stack (app + llama.cpp + whisper + Fish)
# running in WSL. Elevation is NOT required: the services run in WSL as your user.
#
#   .\stop_jarvis.ps1              stop the services, then offer to shut WSL down
#   .\stop_jarvis.ps1 -KeepWsl     stop the services only (use when restarting)
#   .\stop_jarvis.ps1 -Shutdown    stop the services and shut WSL down, no prompt
#
# Shutting WSL down releases the VM's memory, which is worth doing before the
# machine goes off for the night. It is deliberately not automatic: it kills
# EVERY WSL distro and anything else running inside them, so a plain stop before
# a restart should leave the VM up.

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

if ($KeepWsl) {
  Write-Host "`nWSL left running (-KeepWsl). Start again with .\start_jarvis.ps1" -ForegroundColor DarkGray
  return
}

if (-not $Shutdown) {
  # Countdown backstop. Any key cancels; left alone it proceeds, since stopping
  # for the night is the usual reason to run this without arguments.
  Write-Host ""
  Write-Host "Shutting WSL down in 10s to release its memory. Press any key to skip." -ForegroundColor Cyan
  $deadline = (Get-Date).AddSeconds(10)
  $cancelled = $false
  try {
    while ((Get-Date) -lt $deadline) {
      if ($Host.UI.RawUI.KeyAvailable) {
        $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') | Out-Null
        $cancelled = $true
        break
      }
      $left = [int][math]::Ceiling(($deadline - (Get-Date)).TotalSeconds)
      Write-Host -NoNewline "`r  $left... "
      Start-Sleep -Milliseconds 200
    }
  } catch {
    # No interactive console (piped or scheduled): do not shut down on a guess.
    Write-Host "`rNon-interactive session; leaving WSL running." -ForegroundColor DarkGray
    Write-Host "Use -Shutdown to force it, or run: wsl --shutdown" -ForegroundColor DarkGray
    return
  }
  Write-Host "`r              "
  if ($cancelled) {
    Write-Host "Skipped. WSL is still running." -ForegroundColor DarkGray
    return
  }
}

Write-Host "Shutting down WSL..." -ForegroundColor Cyan
wsl --shutdown
Start-Sleep -Seconds 2
Write-Host "WSL shut down. Memory released; safe to power off." -ForegroundColor Green
