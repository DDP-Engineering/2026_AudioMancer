<#
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.IO.Compression.FileSystem

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

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$appRoot = Join-Path $repoRoot '04_Software\AudioMancer'
$deliveryRoot = Join-Path $repoRoot '07_Delivery'
$specPath = Join-Path $scriptRoot 'audiomancer_windows.spec'
$pyprojectPath = Join-Path $appRoot 'pyproject.toml'
$englishUserGuidePath = Join-Path $repoRoot '05_SoftwareDocu\UserGuide'
$romanianUserGuidePath = Join-Path $repoRoot '05_SoftwareDocu\UserGuide_ro'
$promptTemplatePath = Join-Path $appRoot 'prompts'

if (-not (Test-Path $pyprojectPath)) {
    throw "Could not locate pyproject.toml at $pyprojectPath"
}

$pyprojectContent = Get-Content $pyprojectPath -Raw
$versionMatch = [regex]::Match($pyprojectContent, '(?m)^version = "([^"]+)"')
if (-not $versionMatch.Success) {
    throw "Could not read project version from $pyprojectPath"
}

$appVersion = $versionMatch.Groups[1].Value
$artifactBaseName = "AudioMancer_Windows_x64_v$appVersion"
$archivePath = Join-Path $deliveryRoot "$artifactBaseName.zip"
$stagingRoot = Join-Path $scriptRoot '.packaging_tmp'
$stagingPath = Join-Path $stagingRoot $artifactBaseName
$buildPath = Join-Path $appRoot 'build'
$distPath = Join-Path $appRoot 'dist'
$distBundlePath = Join-Path $distPath 'AudioMancer'

$requiredRootFiles = @(
    'settings.json',
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

    if (-not (Test-Path $englishUserGuidePath)) {
        throw "Required English user guide folder is missing: $englishUserGuidePath"
    }
    if (-not (Test-Path $romanianUserGuidePath)) {
        throw "Required Romanian user guide folder is missing: $romanianUserGuidePath"
    }
    if (-not (Test-Path $promptTemplatePath)) {
        throw "Required prompt-template folder is missing: $promptTemplatePath"
    }
    $helpRootPath = Join-Path $stagingPath 'help'
    $helpEnglishPath = Join-Path $helpRootPath 'en'
    $helpRomanianPath = Join-Path $helpRootPath 'ro'
    New-Item -ItemType Directory -Path $helpRootPath -Force | Out-Null
    Copy-Item -LiteralPath $englishUserGuidePath -Destination $helpEnglishPath -Recurse -Force
    Copy-Item -LiteralPath $romanianUserGuidePath -Destination $helpRomanianPath -Recurse -Force
    Copy-Item -LiteralPath $promptTemplatePath -Destination (Join-Path $stagingPath 'prompts') -Recurse -Force

    $startScriptPath = Join-Path $stagingPath 'Start-AudioMancer.cmd'
    @(
        '@echo off'
        'setlocal'
        'cd /d "%~dp0"'
        '"%~dp0AudioMancer.exe" %*'
    ) | Set-Content -LiteralPath $startScriptPath -Encoding ASCII

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
        'Prompt templates are included in prompts\.'
        'Offline help is included in help\en\index.html and help\ro\index.html.'
    ) | Set-Content -LiteralPath $releaseNotesPath -Encoding ASCII
}

Invoke-Step -Name 'Create versioned delivery archive' -Action {
    New-ZipArchiveFromDirectory -SourceDirectory $stagingPath -DestinationArchive $archivePath
}

Invoke-Step -Name 'Clean build artifacts' -Action {
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
