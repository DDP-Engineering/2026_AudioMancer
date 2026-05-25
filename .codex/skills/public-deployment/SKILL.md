---
name: public-deployment
description: Maintain the public AudioMancer delivery repository and release surface. Use when Codex needs to publish, update, audit, or clean up AudioMancer public deployments, GitHub Releases, VoiceWeaver runtime release links, the GitHub Pages download page, or the public README for DDP-Engineering/2026_AudioMancer.
---

# Public Deployment

## Overview

Use this skill for AudioMancer public delivery work in `DDP-Engineering/2026_AudioMancer`. The goal is a simple public surface: one latest AudioMancer release, the latest VoiceWeaver runtime available from releases and linked from AudioMancer, and current download instructions on GitHub Pages and the public README.

## Ground Rules

- Treat `https://github.com/DDP-Engineering/2026_AudioMancer` as the public executable-delivery repository, not the application source repository.
- Keep exactly one current AudioMancer release visible as the latest application delivery.
- Keep the latest VoiceWeaver runtime available from GitHub Releases. If the runtime is too large for one asset, preserve all multipart assets and checksum files.
- Do not delete a release that hosts the only current VoiceWeaver runtime assets unless those assets have first been moved or re-uploaded and all links have been verified.
- Prefer direct GitHub release URLs for durable references. Use `releases/latest/download/...` only for assets that must always follow the latest AudioMancer release.
- Do not publish source code, generated staging folders, or unrelated files to the public delivery repo.
- Do not delete tags unless the user explicitly asks; deleting a release is usually enough.

## Public Targets

- Releases: `https://github.com/DDP-Engineering/2026_AudioMancer/releases`
- Current AudioMancer release: `https://github.com/DDP-Engineering/2026_AudioMancer/releases/tag/v1.3.0` unless a newer version is being published
- GitHub Pages download page: `https://ddp-engineering.github.io/2026_AudioMancer/`
- GitHub Pages source: `docs/index.html` in `DDP-Engineering/2026_AudioMancer`
- Public README: `README.md` in `DDP-Engineering/2026_AudioMancer`
- Local draft page in source workspace: `07_Delivery/Public_GitHub_Page/index.html`
- Local delivery notes in source workspace: `07_Delivery/README.md`

## Standard Workflow

1. Inspect current releases:
   - `gh release list --repo DDP-Engineering/2026_AudioMancer --limit 20`
   - `gh release view <tag> --repo DDP-Engineering/2026_AudioMancer --json name,tagName,assets,body,url`
2. Identify the latest AudioMancer release and the release that hosts the latest VoiceWeaver runtime.
3. If publishing AudioMancer:
   - Upload or replace only the current `AudioMancer_Windows_x64.zip` and `SHA256SUMS.txt` on the latest AudioMancer release.
   - Ensure the release body contains the AudioMancer checksum and points users to the current VoiceWeaver runtime location.
4. If publishing VoiceWeaver:
   - Upload all runtime parts together plus `SHA256SUMS.txt`.
   - Document the reassembled ZIP SHA256 and the PowerShell reassembly command.
   - Update the latest AudioMancer release body to link to the runtime.
5. Remove or clean old AudioMancer releases only after checking they do not host required VoiceWeaver assets.
6. Update public instructions when links, checksums, install steps, or runtime location changes:
   - public `README.md`
   - public `docs/index.html`
   - local `07_Delivery/Public_GitHub_Page/index.html`
   - local `07_Delivery/README.md`
7. Verify with GitHub after changes:
   - release list shows only the intended AudioMancer release plus any runtime-only release
   - release assets are correct
   - public README has no stale old-release links
   - `docs/index.html` has no stale old-release links
   - GitHub Pages reports `status: built` from `master:/docs`

## Cleanup Rules

- If an older release contains only obsolete AudioMancer assets, delete the release with `gh release delete <tag> --repo DDP-Engineering/2026_AudioMancer --yes`.
- If an older release contains VoiceWeaver assets, keep the release or move the assets first. Rename it to a runtime package if needed.
- If a runtime release also contains an obsolete `AudioMancer_Windows_x64.zip`, delete only that asset through the GitHub asset API and leave runtime assets intact.
- After cleanup, the public releases page should show one latest AudioMancer release and the current VoiceWeaver runtime release if runtime assets are hosted separately.

## Link Policy

- AudioMancer download buttons should point to the latest AudioMancer release page or `releases/latest/download/AudioMancer_Windows_x64.zip`.
- VoiceWeaver instructions should point users through the latest AudioMancer release page when that page carries the current runtime links.
- Avoid directing users to older AudioMancer versions. If a tag remains only because it hosts VoiceWeaver, label it clearly as VoiceWeaver runtime.
- When release tag numbers differ from package versions, be explicit: for example, tag `v1.0.0` may host `VoiceWeaver v1.5.0`.

## Verification Commands

Use these as appropriate:

```powershell
gh release list --repo DDP-Engineering/2026_AudioMancer --limit 20
gh release view v1.3.0 --repo DDP-Engineering/2026_AudioMancer --json name,tagName,assets,body,url
gh api repos/DDP-Engineering/2026_AudioMancer/pages
```

To check public files for stale old-release links:

```powershell
$r = gh api repos/DDP-Engineering/2026_AudioMancer/contents/README.md --jq .content
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($r -join ''))) |
    Select-String -Pattern 'releases/download/v1\.0\.|releases/tag/v1\.0\.'

$p = gh api repos/DDP-Engineering/2026_AudioMancer/contents/docs/index.html --jq .content
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($p -join ''))) |
    Select-String -Pattern 'releases/download/v1\.0\.|releases/tag/v1\.0\.'
```

## Final Response

Report:
- which releases remain
- which releases or assets were deleted
- whether VoiceWeaver runtime assets remain reachable
- which public files were updated
- what was verified and what remains unverified
