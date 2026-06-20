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
