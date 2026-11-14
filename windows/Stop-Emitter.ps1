#Requires -Version 5.1
#Requires -RunAsAdministrator
param([string]$TaskName = 'CanaryPDM')
$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ((Get-ScheduledTask -TaskName $TaskName).State -eq 'Running') {
        if ($timer.Elapsed.TotalSeconds -gt 15) { throw 'Task did not stop; inspect it before restarting.' }
        Start-Sleep -Milliseconds 250
    }
}
