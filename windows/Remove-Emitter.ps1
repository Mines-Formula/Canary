#Requires -Version 5.1
#Requires -RunAsAdministrator
param([string]$TaskName = 'CanaryPDM')
$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    & (Join-Path $PSScriptRoot 'Stop-Emitter.ps1') -TaskName $TaskName
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Write-Output 'Scheduled task removed. Application, private configuration, and logs were retained.'
