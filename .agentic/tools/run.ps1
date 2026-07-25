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
$Launcher = Join-Path $ScriptDir "run_aegis.py"

# @brief Resolve explicit, WAEGIS-registered, then system Python.
# @return Hashtable containing Command and leading Args, or $null.
function Resolve-Python {
    if (-not [string]::IsNullOrWhiteSpace($env:AEGIS_PYTHON)) {
        return @{ Command = $env:AEGIS_PYTHON; Args = @() }
    }
    $WaegisHome = $env:WAEGIS_HOME
    if ([string]::IsNullOrWhiteSpace($WaegisHome)) {
        $Base = $env:APPDATA
        if ([string]::IsNullOrWhiteSpace($Base)) {
            $Base = Join-Path $HOME "AppData\Roaming"
        }
        $WaegisHome = Join-Path $Base "waegis"
    }
    $Pointer = Join-Path $WaegisHome "runtime-python"
    if (Test-Path -LiteralPath $Pointer -PathType Leaf) {
        $Registered = (Get-Content -LiteralPath $Pointer -Raw).Trim()
        if (-not [string]::IsNullOrWhiteSpace($Registered) -and (Test-Path -LiteralPath $Registered -PathType Leaf)) {
            return @{ Command = $Registered; Args = @() }
        }
    }
    $candidates = @(
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Command -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $candidate
        }
    }
    return $null
}

$Interpreter = Resolve-Python
if ($null -eq $Interpreter) {
    # -ErrorAction Continue, then an explicit exit. Under the script-level
    # $ErrorActionPreference = "Stop" a plain Write-Error raises a terminating
    # error and ends the script with status 1, never reaching this exit and
    # disagreeing with run.sh's 2 for the identical condition. A .NET call such
    # as [Console]::Error.WriteLine would also report correctly, but it is a
    # method invocation and fails outright under PowerShell Constrained
    # Language Mode - the configuration a locked-down corporate host is most
    # likely to be running, and precisely where this message matters most.
    Write-Error "No AEGIS Python runtime is available. Run a packaged WAEGIS command or set AEGIS_PYTHON." -ErrorAction Continue
    exit 2
}

& $Interpreter.Command @($Interpreter.Args) $Launcher @Args
exit $LASTEXITCODE
