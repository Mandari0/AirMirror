# AirMirror firewall + network setup (must run as Administrator)
param(
    [string]$UxPlay = 'C:\msys64\ucrt64\bin\uxplay.exe'
)
$ErrorActionPreference = 'Stop'

Write-Host "=== AirMirror setup ===" -ForegroundColor Cyan

if (-not (Test-Path $UxPlay)) {
    Write-Host "ERROR: uxplay.exe not found at $UxPlay" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# 1) Inbound firewall rule for uxplay.exe (Private networks only)
$ruleName = 'AirMirror (UxPlay)'
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Firewall rule '$ruleName' already exists - updating."
    $existing | Remove-NetFirewallRule
}
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound `
    -Program $UxPlay -Action Allow -Profile Private -Protocol Any | Out-Null
Write-Host "OK: inbound firewall rule for uxplay.exe added." -ForegroundColor Green

# 2) Offer to switch the LAN adapter to the Private network profile
$eth = Get-NetConnectionProfile | Where-Object { $_.InterfaceAlias -eq 'Ethernet' }
if ($eth) {
    Write-Host ("Ethernet network category: " + $eth.NetworkCategory)
    if ($eth.NetworkCategory -eq 'Public') {
        $answer = Read-Host "Switch Ethernet to Private so the iPhone can discover this PC? (y/n)"
        if ($answer -match '^(y|Y|д|Д)') {
            Set-NetConnectionProfile -InterfaceAlias 'Ethernet' -NetworkCategory Private
            Write-Host "OK: Ethernet is now Private." -ForegroundColor Green
        } else {
            Write-Host "Skipped. Discovery may not work while the network is Public." -ForegroundColor Yellow
        }
    }
}

# 3) Show the current network profiles for a quick sanity check
Write-Host ""
Write-Host "Current network profiles:" -ForegroundColor Cyan
Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory | Format-Table -AutoSize

Write-Host "Done. Start AirMirror from the Start menu or the tray icon." -ForegroundColor Green
Read-Host "Press Enter to close"
