#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_text_analysis_service.py
@brief Shared workflow access to pure Cleanup text helpers.
@details Other application workflows reuse this public API; processing lives in cleanup.text.
"""

# IMPORTS

from audiomancer.cleanup.text import (
    classify_text_script as classify_text_script,
)
from audiomancer.cleanup.text import (
    detect_chapter_label as detect_chapter_label,
)
from audiomancer.cleanup.text import (
    detect_language as detect_language,
)
from audiomancer.cleanup.text import (
    has_sentence_terminal as has_sentence_terminal,
)
from audiomancer.cleanup.text import (
    is_scene_separator_artifact as is_scene_separator_artifact,
)
from audiomancer.cleanup.text import (
    normalize_text_line as normalize_text_line,
)
from audiomancer.cleanup.text import (
    normalized_compare_key as normalized_compare_key,
)
from audiomancer.cleanup.text import (
    normalized_header_footer_key as normalized_header_footer_key,
)
from audiomancer.cleanup.text import (
    sentence_spans as sentence_spans,
)

# END OF FILE
