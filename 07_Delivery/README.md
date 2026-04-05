<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 07_Delivery

Release packaging, delivery bundles, and distribution artifacts.

Current Windows delivery artifacts are produced by:

- `../02_Tools/package_windows_release.ps1`

The expected archive naming pattern is:

- `AudioMancer_Windows_x64_v<version>.zip`

The delivery zip contains the portable Windows application bundle together with
`settings.json` and the four license files required by the app root.

