#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file markdown.py
@brief MARKDOWN structural extraction.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from markdown_it import MarkdownIt

from ..encoding import _read_text_with_fallback
from ..models import ExtractionAdapterResult, SourceEvent, _emit_adapter_progress
from ..models import check_cancelled as raise_if_cancelled
from .html_content import _heading_level, _StructuredHtmlExtractor

# PUBLIC API


def _extract_markdown(
    source_path: Path,
    *,
    progress_callback=None,
    cancel_requested=None,
) -> ExtractionAdapterResult:
    """@brief Extract reader-facing CommonMark blocks with native structural roles."""
    raise_if_cancelled(cancel_requested)
    text, encoding = _read_text_with_fallback(source_path)
    tokens = MarkdownIt("commonmark").parse(text)
    events: list[SourceEvent] = []
    stack: list[str] = []
    heading_level: int | None = None
    list_depth = 0
    blockquote_depth = 0

    for token_index, token in enumerate(tokens):
        raise_if_cancelled(cancel_requested)
        token_type = token.type
        if token_type.endswith("_open"):
            stack.append(token_type)
            if token_type == "heading_open":
                heading_level = _heading_level(token.tag)
            elif token_type in {"bullet_list_open", "ordered_list_open"}:
                list_depth += 1
            elif token_type == "blockquote_open":
                blockquote_depth += 1
            continue
        if token_type.endswith("_close"):
            if token_type == "heading_close":
                heading_level = None
            elif token_type in {"bullet_list_close", "ordered_list_close"}:
                list_depth = max(0, list_depth - 1)
            elif token_type == "blockquote_close":
                blockquote_depth = max(0, blockquote_depth - 1)
            if stack:
                stack.pop()
            continue
        if token_type == "hr":
            events.append(
                SourceEvent(
                    text="***",
                    kind="separator",
                    structure_origin="native",
                    boundary_before="\n\n",
                    boundary_kind="native_paragraph",
                    locator={"token_index": token_index},
                    native={"tag": "hr"},
                )
            )
            continue
        if token_type in {"fence", "code_block"}:
            code_text = token.content.rstrip("\n")
            if code_text:
                events.append(
                    SourceEvent(
                        text=code_text,
                        kind="table_or_preformatted",
                        structure_origin="native",
                        boundary_before="\n\n",
                        boundary_kind="native_paragraph",
                        locator={"token_index": token_index},
                        native={"tag": token.tag or token_type, "info": str(token.info or "")},
                    )
                )
            continue
        if token_type == "html_block":
            parser = _StructuredHtmlExtractor(spine_index=0, item_id="markdown")
            parser.feed(token.content)
            parser.close()
            events.extend(
                replace(
                    event,
                    locator={"token_index": token_index, "line_map": list(token.map or []), "html_block_index": index},
                )
                for index, event in enumerate(parser.events)
            )
            continue
        if token_type != "inline":
            continue
        visible_text = _markdown_inline_text(token)
        if not visible_text.strip():
            continue
        if heading_level is not None:
            kind = "heading"
        elif list_depth:
            kind = "list_or_dialogue"
        elif blockquote_depth:
            kind = "blockquote"
        else:
            kind = "body"
        events.append(
            SourceEvent(
                text=visible_text.strip(),
                kind=kind,
                structure_origin="native",
                boundary_before="\n\n",
                boundary_kind="native_paragraph",
                locator={"token_index": token_index, "line_map": list(token.map or [])},
                native={
                    "tag": token.tag or "inline",
                    "heading_level": heading_level,
                    "list_level": list_depth or None,
                    "blockquote_depth": blockquote_depth or None,
                },
            )
        )

    _emit_adapter_progress(progress_callback, 1, 1, "Markdown structure parsed.")
    return ExtractionAdapterResult(
        events=events,
        warnings=[],
        pages=[],
        structure_quality="native",
        eligibility_mode="native",
        eligibility_reason_codes=[],
        encoding=encoding,
        progress_total=1,
        page_count=None,
    )


def _markdown_inline_text(token) -> str:
    """@brief Return visible inline text without Markdown delimiters."""
    if not token.children:
        return str(token.content)
    parts: list[str] = []
    for child in token.children:
        if child.type in {"text", "code_inline"}:
            parts.append(str(child.content))
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
        elif child.type == "image":
            parts.append(str(child.content))
    return "".join(parts)


# END OF FILE
