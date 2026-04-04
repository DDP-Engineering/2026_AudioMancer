<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Packaging Placeholders

This folder contains placeholder build helpers for future `PyInstaller`-based
packaging.

Current intended flow:

1. sync the environment with `uv`
2. run the focused automated tests
3. run the future `PyInstaller` build command
4. zip the generated output folder for delivery

These scripts are placeholders only. They do not yet implement a concrete
`PyInstaller` spec or release workflow.
