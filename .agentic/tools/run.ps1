<#
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$Launcher = Join-Path $ScriptDir "run_agentic_workflow.py"

function Resolve-Python {
    $candidates = @(
        (Join-Path $ProjectRoot "04_Software\AudioMancer\.venv\Scripts\python.exe"),
        "python",
        "py"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $candidate
        }
    }
    return $null
}

$Python = Resolve-Python
if ($null -eq $Python) {
    Write-Error "Python 3.11+ was not found. Install Python 3.11+ or install uv, then rerun this script."
}

& $Python $Launcher @Args
exit $LASTEXITCODE
