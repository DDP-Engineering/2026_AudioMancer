#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_pytest_runtime_configuration.py
@brief Verify safeguards applied to the AudioMancer pytest runtime.
@details Confirms that individual tests cannot hang indefinitely and consume
         the complete test-suite time budget.
"""

# TESTS


def test_individual_tests_have_a_windows_safe_timeout(pytestconfig) -> None:
    """
    @brief      Verify the timeout plugin and repository-wide test limit.
    @param[in]  pytestconfig Active pytest configuration.
    @return     None.
    @exception  None.
    """
    assert pytestconfig.pluginmanager.hasplugin("timeout")
    assert pytestconfig.getini("timeout") == "120"
    assert pytestconfig.getini("timeout_method") == "thread"


def test_parallel_execution_is_available_and_opt_in(pytestconfig) -> None:
    """
    @brief      Verify local worker support without enabling it by default.
    @param[in]  pytestconfig Active pytest configuration.
    @return     None.
    @exception  None.
    """
    configured_options = pytestconfig.getini("addopts")

    assert pytestconfig.pluginmanager.hasplugin("xdist")
    assert "-n" not in configured_options
    assert not any(option.startswith("--numprocesses") for option in configured_options)


# END OF FILE
