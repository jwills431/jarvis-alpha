# jarvis_firewall_rule.ps1 - allow JARVIS on the private LAN only.
# RUN AS ADMINISTRATOR (right-click -> Run with PowerShell, or from an elevated prompt).
#
# Opens inbound TCP 8787 ONLY to devices on this machine's own subnet
# (192.168.4.0/22, which is what 192.168.7.83/22 belongs to). Anything outside the
# LAN - including the internet - is still refused. Combined with TLS + HTTP Basic
# auth in JARVIS itself, that is the full private-hosting boundary.
#
# To remove later:  Remove-NetFirewallRule -DisplayName "JARVIS (private LAN)"

#Requires -RunAsAdministrator

$port   = 8787
$subnet = '192.168.4.0/22'   # covers 192.168.4.1 - 192.168.7.254
$name   = 'JARVIS (private LAN)'

Write-Host "Creating firewall rule '$name'..." -ForegroundColor Cyan

# Replace any previous copy so re-running is safe.
Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule

New-NetFirewallRule `
  -DisplayName $name `
  -Description "Allow JARVIS web UI from devices on the local subnet only." `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort $port `
  -RemoteAddress $subnet `
  -Profile Any | Out-Null

Write-Host "`nRule created:" -ForegroundColor Green
Get-NetFirewallRule -DisplayName $name |
  Format-List DisplayName, Enabled, Direction, Action, Profile

Write-Host "Scope (only these remote addresses may connect):" -ForegroundColor Green
Get-NetFirewallRule -DisplayName $name | Get-NetFirewallAddressFilter |
  Format-List RemoteAddress

Write-Host "Port:" -ForegroundColor Green
Get-NetFirewallRule -DisplayName $name | Get-NetFirewallPortFilter |
  Format-List Protocol, LocalPort

Write-Host "`nDone. JARVIS will be reachable at https://192.168.7.83:$port from your LAN." -ForegroundColor Green
Write-Host "Note: this Wi-Fi is currently classified 'Public'. For a home network," -ForegroundColor DarkGray
Write-Host "      'Private' is more appropriate. To change it (optional):" -ForegroundColor DarkGray
Write-Host "      Set-NetConnectionProfile -InterfaceAlias 'Wi-Fi' -NetworkCategory Private" -ForegroundColor DarkGray
