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

# Prefer the py launcher — the reliable python.org entry point that the
# Microsoft Store 'App execution alias' stubs do not shadow.
$launcher = Get-Command "py" -ErrorAction SilentlyContinue
if ($launcher) {
  $exe = $launcher.Source
  $prefix = @("-3")
}

# Fall back to python3/python, but skip the WindowsApps alias stubs (which
# just open the Microsoft Store instead of running Python).
if (-not $exe) {
  foreach ($candidate in @("python3", "python")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd -and ($cmd.Source -notlike "*\WindowsApps\*")) {
      $exe = $cmd.Source
      break
    }
  }
}

if (-not $exe) {
  Write-Error "Python 3 not found. Install from https://www.python.org/ or the Microsoft Store."
}

& $exe @prefix $scriptPath @args
exit $LASTEXITCODE
