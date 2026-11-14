#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [string]$AppDirectory = (Split-Path $PSScriptRoot -Parent),
    [string]$ConfigPath = 'C:\ProgramData\Canary\emitter.toml',
    [string]$TaskName = 'CanaryPDM'
)
$ErrorActionPreference = 'Stop'
$AppDirectory = (Resolve-Path -LiteralPath $AppDirectory).Path
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
& $PythonPath -c 'import sys; assert sys.version_info[:2] in ((3, 12), (3, 13)), "Python 3.12 or 3.13 is required"'
if ($LASTEXITCODE -ne 0) { throw 'Install a machine-accessible Python 3.13 interpreter (recommended) or Python 3.12 first.' }
$venvDirectory = Join-Path $AppDirectory '.venv'
$venvPython = Join-Path $venvDirectory 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonPath -m venv $venvDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $venvPython -c 'import sys; assert sys.version_info[:2] in ((3, 12), (3, 13)), "Virtual environment must use Python 3.12 or 3.13"'
if ($LASTEXITCODE -ne 0) { throw 'Existing virtual environment is not Python 3.12 or 3.13.' }
& $venvPython -m pip install -r (Join-Path $AppDirectory 'requirements-emitter.txt')
if ($LASTEXITCODE -ne 0) { throw 'Emitter dependency installation failed.' }

# Replace the private file's access rules rather than keeping broad inherited grants.
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
    $identity = New-Object System.Security.Principal.SecurityIdentifier($sid)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $ConfigPath -AclObject $acl

Push-Location $AppDirectory
try {
    & $venvPython -m emitter.windows --config $ConfigPath --check
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; task was not registered. Check configuration, drives, and EC2 access.' }
} finally { Pop-Location }

$action = New-ScheduledTaskAction -Execute $venvPython -Argument "-m emitter.windows --config `"$ConfigPath`"" -WorkingDirectory $AppDirectory
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    & (Join-Path $PSScriptRoot 'Stop-Emitter.ps1') -TaskName $TaskName
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "Installed and started $TaskName. Confirm task status and logs after startup and after reboot."
