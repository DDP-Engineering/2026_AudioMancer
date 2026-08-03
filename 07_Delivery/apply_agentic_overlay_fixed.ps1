$ErrorActionPreference = "Stop"

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$overlay = "$repo\07_Delivery\agentic_workflow_sync_overlay"

$repoResolved = $repo

if (-not (Test-Path -LiteralPath (Join-Path $repoResolved ".git"))) {
  throw "Expected a Git repository root: $repoResolved"
}
if (-not (Test-Path -LiteralPath $overlay -PathType Container)) {
  throw "Agentic overlay directory not found: $overlay"
}
$overlayResolved = (Resolve-Path -LiteralPath $overlay).Path
if (-not $overlayResolved.StartsWith($repoResolved)) {
  throw "Unexpected overlay path: $overlayResolved"
}

function Ensure-Directory($path) {
  if (-not (Test-Path -LiteralPath $path)) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
  }
}

function Copy-File($relative) {
  $from = Join-Path $overlay $relative
  $to = Join-Path $repo $relative
  Ensure-Directory (Split-Path -Parent $to)
  Copy-Item -LiteralPath $from -Destination $to -Force
}

function Copy-DirectoryContents($relative) {
  $from = Join-Path $overlay $relative
  $to = Join-Path $repo $relative
  Ensure-Directory $to
  Copy-Item -Path (Join-Path $from "*") -Destination $to -Recurse -Force -Exclude ".pytest_cache","__pycache__","*.pyc"
}

function Remove-AccidentalDirectory($relative) {
  $target = Join-Path $repo $relative
  if (-not (Test-Path -LiteralPath $target)) {
    return
  }
  $resolved = (Resolve-Path -LiteralPath $target).Path
  if (-not $resolved.StartsWith($repoResolved)) {
    throw "Refusing to remove outside repo: $resolved"
  }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

Remove-AccidentalDirectory ".agentic\cli\cli"
Remove-AccidentalDirectory ".agentic\hooks\hooks"
Remove-AccidentalDirectory ".agentic\tools\tools"
Remove-AccidentalDirectory ".agentic\skills\skills"
Remove-AccidentalDirectory ".agentic\documents\documents"

Copy-File ".agentic\workflow.toml"
Copy-DirectoryContents ".agentic\cli"
Copy-DirectoryContents ".agentic\tools"
Copy-DirectoryContents ".agentic\hooks"
Copy-DirectoryContents ".agentic\skills"
Copy-DirectoryContents ".agentic\documents"

$oldPackagedHooks = "$repo\.agentic\cli\src\agentic_workflow\hooks"
if (Test-Path -LiteralPath $oldPackagedHooks) {
  $resolvedOldHooks = (Resolve-Path -LiteralPath $oldPackagedHooks).Path
  if (-not $resolvedOldHooks.StartsWith($repoResolved)) {
    throw "Refusing to remove outside repo: $resolvedOldHooks"
  }
  Remove-Item -LiteralPath $resolvedOldHooks -Recurse -Force
}

Copy-File ".codex\config.toml"
Copy-File ".codex\hooks.json"

$skills = @(
  "agentic-development",
  "agentic-delivery",
  "documentation-audit",
  "python-codestyle-audit",
  "regression-traceability",
  "write-component-documentation"
)

foreach ($skill in $skills) {
  Copy-File ".codex\skills\$skill\SKILL.md"
  Copy-File ".claude\skills\$skill\SKILL.md"
}

Copy-File ".claude\settings.json"
Copy-File ".claude\README.md"
Copy-File ".claude\agents\README.md"

Copy-File "AGENTS.md"
Copy-Item -LiteralPath "$overlay\CLAUDE.md" -Destination "$repo\claude.md" -Force

Write-Host "Agentic overlay applied successfully."
