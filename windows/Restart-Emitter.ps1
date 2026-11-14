#Requires -Version 5.1
#Requires -RunAsAdministrator
param([string]$TaskName = 'CanaryPDM')
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Stop-Emitter.ps1') -TaskName $TaskName
Start-ScheduledTask -TaskName $TaskName
