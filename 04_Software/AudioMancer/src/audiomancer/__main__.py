#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file __main__.py
@brief Module entrypoint for launching AudioMancer with python -m.
@details Delegates process startup to the application main entrypoint.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.0
"""

# IMPORTS

from .app import main

# PUBLIC API

if __name__ == "__main__":
    raise SystemExit(main())

# END OF FILE
