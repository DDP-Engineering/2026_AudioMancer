<#
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.IO.Compression.FileSystem

# Run each release step with a visible label so packaging failures identify the
# stage that failed in the PowerShell output.
function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host "==> $Name"
    & $Action
}

# Recreate the stable delivery zip from a prepared staging directory.
function New-ZipArchiveFromDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceDirectory,
        [Parameter(Mandatory = $true)]
        [string]$DestinationArchive
    )

    if (Test-Path $DestinationArchive) {
        Remove-Item -LiteralPath $DestinationArchive -Force
    }

    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $SourceDirectory,
        $DestinationArchive,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true
    )
}

# Copy settings into a delivery package without operator-local secrets or
# connection-discovery cache. The source settings.json in the app root is not
# modified.
function Copy-CleanSettingsFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    $settingsPayload = Get-Content -LiteralPath $SourcePath -Raw | ConvertFrom-Json

    if ($settingsPayload.PSObject.Properties.Name -contains 'llm_profiles') {
        foreach ($profile in $settingsPayload.llm_profiles) {
            if ($profile.PSObject.Properties.Name -contains 'api_key') {
                $profile.api_key = ''
            }
            if (
                ($profile.PSObject.Properties.Name -contains 'backend_kind') -and
                ($profile.PSObject.Properties.Name -contains 'base_url') -and
                $profile.backend_kind -eq 'lmstudio'
            ) {
                $profile.base_url = 'http://127.0.0.1:1234/v1'
            }
            if ($profile.PSObject.Properties.Name -contains 'discovered_model_name') {
                $profile.discovered_model_name = ''
            }
            if ($profile.PSObject.Properties.Name -contains 'discovered_context_window') {
                $profile.discovered_context_window = $null
            }
            if ($profile.PSObject.Properties.Name -contains 'discovery_succeeded') {
                $profile.discovery_succeeded = $false
            }
            if ($profile.PSObject.Properties.Name -contains 'discovery_message') {
                $profile.discovery_message = ''
            }
        }
    }

    if ($settingsPayload.PSObject.Properties.Name -contains 'tts_runtime_base_url') {
        $settingsPayload.tts_runtime_base_url = 'http://127.0.0.1:8059'
    }
    if ($settingsPayload.PSObject.Properties.Name -contains 'tts_runtime_api_key') {
        $settingsPayload.tts_runtime_api_key = ''
    }
    if ($settingsPayload.PSObject.Properties.Name -contains 'tts_runtime_probe_succeeded') {
        $settingsPayload.tts_runtime_probe_succeeded = $false
    }
    if ($settingsPayload.PSObject.Properties.Name -contains 'tts_runtime_probe_message') {
        $settingsPayload.tts_runtime_probe_message = ''
    }
    if ($settingsPayload.PSObject.Properties.Name -contains 'tts_runtime_discovered_models') {
        $settingsPayload.tts_runtime_discovered_models = @()
    }
    if ($settingsPayload.PSObject.Properties.Name -contains 'tts_runtime_active_model_id') {
        $settingsPayload.tts_runtime_active_model_id = $null
    }
    if ($settingsPayload.PSObject.Properties.Name -contains 'tts_runtime_device_diagnostics') {
        $settingsPayload.tts_runtime_device_diagnostics = [pscustomobject]@{}
    }

    $settingsPayload |
        ConvertTo-Json -Depth 100 |
        Set-Content -LiteralPath $DestinationPath -Encoding UTF8
}

# Resolve repository paths from the script location so the script can be run
# from any current working directory.
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$appRoot = Join-Path $repoRoot '04_Software\AudioMancer'
$deliveryRoot = Join-Path $repoRoot '07_Delivery'
$specPath = Join-Path $scriptRoot 'audiomancer_windows.spec'
$pyprojectPath = Join-Path $appRoot 'pyproject.toml'
$changelogPath = Join-Path $repoRoot 'CHANGELOG.md'
$englishUserGuidePath = Join-Path $repoRoot '05_SoftwareDocu\UserGuide'
$romanianUserGuidePath = Join-Path $repoRoot '05_SoftwareDocu\UserGuide_ro'
$promptTemplatePath = Join-Path $appRoot 'prompts'

if (-not (Test-Path $pyprojectPath)) {
    throw "Could not locate pyproject.toml at $pyprojectPath"
}
if (-not (Test-Path $changelogPath)) {
    throw "Could not locate CHANGELOG.md at $changelogPath"
}

# The archive filename is stable, but release notes still include the app
# version read from pyproject.toml.
$pyprojectContent = Get-Content $pyprojectPath -Raw
$versionMatch = [regex]::Match($pyprojectContent, '(?m)^version = "([^"]+)"')
if (-not $versionMatch.Success) {
    throw "Could not read project version from $pyprojectPath"
}

$appVersion = $versionMatch.Groups[1].Value
$artifactBaseName = 'AudioMancer_Windows_x64'
$archivePath = Join-Path $deliveryRoot "$artifactBaseName.zip"
$stagingRoot = Join-Path $scriptRoot '.packaging_tmp'
$stagingPath = Join-Path $stagingRoot $artifactBaseName
$buildPath = Join-Path $appRoot 'build'
$distPath = Join-Path $appRoot 'dist'
$distBundlePath = Join-Path $distPath 'AudioMancer'

# Files copied next to the executable so the portable bundle is self-contained.
$requiredRootFiles = @(
    'pyproject.toml',
    'LICENSE.txt',
    'LICENSE_NC.txt',
    'LICENSE_ro.txt',
    'LICENSE_NC_ro.txt'
)

Invoke-Step -Name 'Prepare packaging workspace' -Action {
    if (-not (Test-Path $deliveryRoot)) {
        New-Item -ItemType Directory -Path $deliveryRoot | Out-Null
    }
    if (Test-Path $stagingPath) {
        Remove-Item -LiteralPath $stagingPath -Recurse -Force
    }
    if (-not (Test-Path $stagingRoot)) {
        New-Item -ItemType Directory -Path $stagingRoot | Out-Null
    }
}

Push-Location $appRoot
try {
    # PyInstaller runs inside the uv-managed app environment.
    Invoke-Step -Name 'Sync uv environment' -Action {
        & uv sync --extra dev
    }

    Invoke-Step -Name 'Build Windows bundle with PyInstaller' -Action {
        if (Test-Path $buildPath) {
            Remove-Item -LiteralPath $buildPath -Recurse -Force
        }
        if (Test-Path $distPath) {
            Remove-Item -LiteralPath $distPath -Recurse -Force
        }
        & uv run --no-sync pyinstaller --noconfirm --clean $specPath
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $distBundlePath)) {
    throw "PyInstaller output folder not found: $distBundlePath"
}

Invoke-Step -Name 'Assemble delivery staging folder' -Action {
    # Start from PyInstaller output, then add project-controlled runtime assets.
    New-Item -ItemType Directory -Path $stagingPath | Out-Null
    Get-ChildItem -LiteralPath $distBundlePath -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $stagingPath -Recurse -Force
    }

    foreach ($fileName in $requiredRootFiles) {
        $sourcePath = Join-Path $appRoot $fileName
        if (-not (Test-Path $sourcePath)) {
            throw "Required packaging file is missing: $sourcePath"
        }
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $stagingPath $fileName) -Force
    }
    Copy-Item -LiteralPath $changelogPath -Destination (Join-Path $stagingPath 'CHANGELOG.md') -Force
    $settingsSourcePath = Join-Path $appRoot 'settings.json'
    if (-not (Test-Path $settingsSourcePath)) {
        throw "Required packaging file is missing: $settingsSourcePath"
    }
    Copy-CleanSettingsFile `
        -SourcePath $settingsSourcePath `
        -DestinationPath (Join-Path $stagingPath 'settings.json')

    if (-not (Test-Path $englishUserGuidePath)) {
        throw "Required English user guide folder is missing: $englishUserGuidePath"
    }
    if (-not (Test-Path $romanianUserGuidePath)) {
        throw "Required Romanian user guide folder is missing: $romanianUserGuidePath"
    }
    if (-not (Test-Path $promptTemplatePath)) {
        throw "Required prompt-template folder is missing: $promptTemplatePath"
    }
    # Offline help is shipped under language-specific folders used by the app.
    $helpRootPath = Join-Path $stagingPath 'help'
    $helpEnglishPath = Join-Path $helpRootPath 'en'
    $helpRomanianPath = Join-Path $helpRootPath 'ro'
    New-Item -ItemType Directory -Path $helpRootPath -Force | Out-Null
    Copy-Item -LiteralPath $englishUserGuidePath -Destination $helpEnglishPath -Recurse -Force
    Copy-Item -LiteralPath $romanianUserGuidePath -Destination $helpRomanianPath -Recurse -Force
    Copy-Item -LiteralPath $promptTemplatePath -Destination (Join-Path $stagingPath 'prompts') -Recurse -Force

    # Keep a simple batch launcher for users who prefer a stable start file.
    $startScriptPath = Join-Path $stagingPath 'Start-AudioMancer.cmd'
    @(
        '@echo off'
        'setlocal'
        'cd /d "%~dp0"'
        '"%~dp0AudioMancer.exe" %*'
    ) | Set-Content -LiteralPath $startScriptPath -Encoding ASCII

    # Plain-text release notes remain readable in the extracted portable folder.
    $releaseNotesPath = Join-Path $stagingPath 'README_RELEASE.txt'
    @(
        "AudioMancer Windows x64 v$appVersion"
        ''
        'This folder is a portable AudioMancer release.'
        ''
        'Start:'
        '- Double-click AudioMancer.exe, or'
        '- Double-click Start-AudioMancer.cmd.'
        ''
        'Install:'
        '- Extract the full zip folder before starting the app.'
        '- Keep the files together; the executable depends on bundled runtime files.'
        ''
        'Configuration and licenses are included next to the executable.'
        'The project changelog is included as CHANGELOG.md.'
        'The packaged settings.json is cleaned of operator API keys and runtime discovery cache.'
        'Prompt templates are included in prompts\.'
        'Offline help is included in help\en\index.html and help\ro\index.html.'
    ) | Set-Content -LiteralPath $releaseNotesPath -Encoding ASCII
}

Invoke-Step -Name 'Create delivery archive' -Action {
    New-ZipArchiveFromDirectory -SourceDirectory $stagingPath -DestinationArchive $archivePath
}

Invoke-Step -Name 'Clean build artifacts' -Action {
    # Do not leave PyInstaller or staging folders in the working tree.
    foreach ($path in @($buildPath, $distPath, $stagingPath)) {
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
    if ((Test-Path $stagingRoot) -and -not (Get-ChildItem -LiteralPath $stagingRoot -Force | Select-Object -First 1)) {
        Remove-Item -LiteralPath $stagingRoot -Force
    }
}

Write-Host "Windows delivery archive created: $archivePath"
