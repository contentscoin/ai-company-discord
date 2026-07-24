#Requires -Version 5.1
<#
.SYNOPSIS
  Windows wrapper for companyctl.py (Python 3, standard library only).
.EXAMPLE
  .\scripts\companyctl.ps1 validate
  .\scripts\companyctl.ps1 scaffold
#>
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $dir "companyctl.py"

$exe = $null
$prefix = @()
foreach ($candidate in @("python3", "python")) {
  $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
  if ($cmd) { $exe = $cmd.Source; break }
}
if (-not $exe) {
  $launcher = Get-Command "py" -ErrorAction SilentlyContinue
  if ($launcher) { $exe = $launcher.Source; $prefix = @("-3") }
}
if (-not $exe) {
  Write-Error "Python 3 not found. Install from https://www.python.org/ or the Microsoft Store."
}

& $exe @prefix $scriptPath @args
exit $LASTEXITCODE
