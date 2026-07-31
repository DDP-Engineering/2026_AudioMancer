#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file __main__.py
@brief Module entry point for the agentic workflow CLI.
@details Mirrors the packaged CLI implementation shipped into generated projects.
"""

# IMPORTS

from .cli import main

# PUBLIC API

if __name__ == "__main__":
    main()

# END OF FILE
