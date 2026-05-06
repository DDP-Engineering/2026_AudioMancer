<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 07_Delivery

Release packaging, delivery bundles, and distribution artifacts.

Delivery artifacts are produced by:

- `../02_Tools/package_windows_release.ps1`
- `../02_Tools/package_linux_release.sh`

The expected archive naming patterns are:

- `AudioMancer_Windows_x64_v<version>.zip`
- `AudioMancer_Ubuntu_x64_v<version>.zip`

Each delivery zip contains a portable application folder with:

- the platform-specific `AudioMancer` executable
- a platform start helper, either `Start-AudioMancer.cmd` or
  `start-audiomancer.sh`
- `README_RELEASE.txt`
- `help/en/` and `help/ro/` with the offline HTML user guides and screenshot assets
- `prompts/` with the external AI prompt templates required by AI-assisted
  cleanup, chunking, translation, character discovery, and Speech Blocks
- `settings.json`
- the four license files required by the app root

Build Windows archives on Windows and Ubuntu archives on Ubuntu. PyInstaller
does not create equivalent desktop bundles by cross-compiling from another
operating system.

Packaging scripts do not run application tests. Treat them as release assembly
tools and run the application validation suite before creating release
artifacts.

## Public GitHub Delivery Notes

The public executable-only delivery project is:

- GitHub repository: `https://github.com/DDP-Engineering/2026_AudioMancer`
- GitHub Pages download page: `https://ddp-engineering.github.io/2026_AudioMancer/`
- Current release page: `https://github.com/DDP-Engineering/2026_AudioMancer/releases/tag/v1.0.0`

Publish only when the project owner gives specific, clear instructions to
publish. Do not publish automatically after packaging, testing, documentation
changes, or normal development work.

The current public delivery is Windows-only. Do not publish Linux artifacts
unless the project owner explicitly asks for a Linux release.

The public GitHub project is used for executable delivery and the download
webpage only. Do not push the application source tree there as part of the
binary publishing workflow.

AudioMancer requires the companion VoiceWeaver runtime for local voice
generation. The VoiceWeaver delivery archive is produced from:

- `D:\ProjectsDDP\2026_VoiceWeaver\07_Delivery\`

The current VoiceWeaver Windows package is larger than a single GitHub Release
asset, so it must be split into numbered parts before upload. Publish all parts
together, and publish `SHA256SUMS.txt` with:

- the AudioMancer delivery archive hash
- the original reassembled VoiceWeaver archive hash
- every published VoiceWeaver part hash

Use GitHub Release assets for executable archives and large binary parts. Do
not commit delivery archives or split archive parts into Git history.

Typical publishing steps are:

1. Build or collect the approved delivery archives.
2. Compute SHA256 hashes for every delivery file.
3. Split any archive that is too large for a single GitHub Release asset.
4. Create or update the GitHub Release with `gh release create`, `gh release
   upload`, or `gh release edit`.
5. Update the public `README.md` and `docs/index.html` in the GitHub project so
   the download page matches the release assets.
6. Verify the release asset list, GitHub Pages build status, and public download
   URLs.
