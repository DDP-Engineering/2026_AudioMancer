<#
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
#>

param(
    [switch] $UseUv
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$CliRoot = Join-Path $ProjectRoot ".agentic\cli"
$VenvRoot = Join-Path $ProjectRoot ".agentic\.venv"

function Resolve-Python {
    $candidates = @("python", "py")
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $candidate
        }
    }
    return $null
}

$Uv = Get-Command "uv" -ErrorAction SilentlyContinue
if ($UseUv -or $null -ne $Uv) {
    if ($null -eq $Uv) {
        Write-Error "uv was requested but was not found. Install uv or run without -UseUv."
    }
    & uv venv --python 3.11 $VenvRoot
    & uv pip install --python (Join-Path $VenvRoot "Scripts\python.exe") -e $CliRoot
    exit $LASTEXITCODE
}

$Python = Resolve-Python
if ($null -eq $Python) {
    Write-Error "Python 3.11+ was not found. Install Python 3.11+ or install uv, then rerun this script."
}

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 3.11+ is required. Install Python 3.11+ or install uv, then rerun this script."
}

& $Python -m venv $VenvRoot
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
& $VenvPython -m pip install -e $CliRoot
exit $LASTEXITCODE
