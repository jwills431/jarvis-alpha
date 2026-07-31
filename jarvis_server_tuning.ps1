# jarvis_server_tuning.ps1 - finish and verify the server "lean and efficient" checklist.
# RUN AS ADMINISTRATOR (right-click -> Run with PowerShell).
#
# Safe to re-run: everything here is idempotent. It reports what is already done
# and only changes what is missing.
#
#   1. Defender exclusions for the WSL disk + project folder (keeps Defender ON,
#      just stops it rescanning multi-GB model/build files on every access)
#   2. Windows Update active hours + no forced reboot while signed in
#   3. Reports startup-app and power state for confirmation

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Continue'
$wslPath  = "C:\Users\josep\AppData\Local\wsl\{78caa623-7df8-4178-ac2e-afa92de1eb7a}"
$projPath = "D:\Claude Projects\JARVIS AI Assistant"

Write-Host "=== 1. Defender exclusions ===" -ForegroundColor Cyan
$existing = @((Get-MpPreference).ExclusionPath)
foreach ($p in @($wslPath, $projPath)) {
  if ($existing -contains $p) {
    Write-Host "  already excluded: $p" -ForegroundColor DarkGray
  } else {
    Add-MpPreference -ExclusionPath $p
    Write-Host "  added: $p" -ForegroundColor Green
  }
}
Write-Host "  current exclusions:" -ForegroundColor Gray
(Get-MpPreference).ExclusionPath | ForEach-Object { Write-Host "    $_" }
$st = Get-MpComputerStatus
Write-Host "  real-time protection still ON: $($st.RealTimeProtectionEnabled)" -ForegroundColor Gray

Write-Host "`n=== 2. Windows Update ===" -ForegroundColor Cyan
# Active hours: Windows will not auto-restart inside this window.
$ux = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\UX\Settings"
New-Item -Path $ux -Force | Out-Null
Set-ItemProperty -Path $ux -Name "SmartActiveHoursState" -Type DWord -Value 0
Set-ItemProperty -Path $ux -Name "ActiveHoursStart"      -Type DWord -Value 5
Set-ItemProperty -Path $ux -Name "ActiveHoursEnd"        -Type DWord -Value 23
$v = Get-ItemProperty $ux
Write-Host "  active hours: $($v.ActiveHoursStart):00 - $($v.ActiveHoursEnd):00 (smart=$($v.SmartActiveHoursState))" -ForegroundColor Green

# Belt and braces: do not force a restart while a user is signed in (RDP counts).
$au = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
New-Item -Path $au -Force | Out-Null
Set-ItemProperty -Path $au -Name "NoAutoRebootWithLoggedOnUsers" -Type DWord -Value 1
Write-Host "  no forced reboot while signed in: $((Get-ItemProperty $au).NoAutoRebootWithLoggedOnUsers)" -ForegroundColor Green

Write-Host "`n=== 3. Confirmation (no changes) ===" -ForegroundColor Cyan
Write-Host "  power plan:" -ForegroundColor Gray
powercfg /getactivescheme
Write-Host "  startup entries (3 = disabled, 2 = enabled):" -ForegroundColor Gray
foreach ($hive in @("HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
                    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run")) {
  if (Test-Path $hive) {
    (Get-ItemProperty $hive).PSObject.Properties |
      Where-Object { $_.Name -notlike 'PS*' } |
      ForEach-Object { Write-Host "    $($_.Name) = $($_.Value[0])" }
  }
}

Write-Host "`nDone. Lean checklist complete." -ForegroundColor Green
Write-Host "Note: Windows may reset active hours after a feature update - re-run this then." -ForegroundColor DarkGray
