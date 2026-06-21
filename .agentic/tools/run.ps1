<#
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# @brief Project-local Python launcher for the embedded workflow CLI.
$Launcher = Join-Path $ScriptDir "run_agentic_workflow.py"

# @brief Resolve a Python launcher available on PATH.
# @return Command name for Python, or $null when no supported launcher exists.
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

$Python = Resolve-Python
if ($null -eq $Python) {
    Write-Error "Python 3.11+ was not found. Install Python 3.11+ or install uv, then rerun this script."
}

& $Python $Launcher @Args
exit $LASTEXITCODE
