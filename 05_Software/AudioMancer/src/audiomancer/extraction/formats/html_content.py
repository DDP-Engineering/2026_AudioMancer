#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file html_content.py
@brief Visible XHTML content shared by EPUB and Markdown.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from html.parser import HTMLParser

from ..models import SourceEvent

# PUBLIC API

_HTML_VOID_TAGS = frozenset(
    (
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    )
)


class _StructuredHtmlExtractor(HTMLParser):
    """@brief Extract visible block-level text and native roles from XHTML."""

    _BLOCK_KINDS = {
        "body": "body",
        "section": "body",
        "article": "body",
        "main": "body",
        "aside": "body",
        "tr": "body",
        "ul": "body",
        "ol": "body",
        "dl": "body",
        "table": "body",
        "tbody": "body",
        "thead": "body",
        "tfoot": "body",
        "div": "body",
        "p": "body",
        "h1": "heading",
        "h2": "heading",
        "h3": "heading",
        "h4": "heading",
        "h5": "heading",
        "h6": "heading",
        "li": "list_or_dialogue",
        "dt": "body",
        "dd": "body",
        "td": "table_or_preformatted",
        "th": "table_or_preformatted",
        "figcaption": "body",
        "blockquote": "blockquote",
        "pre": "table_or_preformatted",
    }

    def __init__(self, *, spine_index: int, item_id: str) -> None:
        """@brief Track nested block context independently from the current text buffer."""
        super().__init__(convert_charrefs=True)
        self.events: list[SourceEvent] = []
        self.warnings: list[str] = []
        self.has_unrendered_content = False
        self._spine_index = spine_index
        self._item_id = item_id
        self._ignored_tags: list[str] = []
        self._frames: list[str] = []
        self._parts: list[str | None] = []
        self._block_index = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        """@brief Preserve visible nested blocks and skip explicitly hidden subtrees."""
        tag = tag.casefold().rsplit(":", 1)[-1]
        attributes = {key.casefold(): "" if value is None else str(value) for key, value in attrs}
        if tag in {"script", "style"} or (
            tag == "link" and "stylesheet" in attributes.get("rel", "").casefold().split()
        ):
            self.has_unrendered_content = True
        declarations = {}
        for declaration in attributes.get("style", "").split(";"):
            key, separator, value = declaration.partition(":")
            if separator:
                declarations[key.strip().casefold()] = value.strip().casefold().removesuffix("!important").strip()
        hidden_style = declarations.get("display") == "none" or declarations.get("visibility") in {"hidden", "collapse"}
        if tag == "body" and self._ignored_tags and self._ignored_tags[0] == "head":
            self._ignored_tags.clear()
        if self._ignored_tags:
            if tag not in _HTML_VOID_TAGS:
                self._ignored_tags.append(tag)
            return
        if (
            tag in {"head", "title", "script", "style", "nav"}
            or hidden_style
            or "hidden" in attributes
            or attributes.get("aria-hidden", "").strip().casefold() == "true"
        ):
            if tag not in _HTML_VOID_TAGS:
                self._ignored_tags.append(tag)
            return
        if tag == "br":
            self._parts.append(None)
            return
        if tag == "hr":
            self._flush_block()
            self._append_event("***", "separator", tag)
            return
        if tag in self._BLOCK_KINDS:
            self._flush_block()
        if tag not in _HTML_VOID_TAGS:
            self._frames.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        """@brief Balance self-closing elements without leaking ignored context."""
        tag = tag.casefold().rsplit(":", 1)[-1]
        self.handle_starttag(tag, attrs)
        if tag not in _HTML_VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        """@brief Flush a closing block and restore its enclosing context."""
        tag = tag.casefold().rsplit(":", 1)[-1]
        if self._ignored_tags:
            if tag == self._ignored_tags[-1]:
                self._ignored_tags.pop()
            return
        if tag in self._BLOCK_KINDS:
            self._flush_block()
        if tag in self._frames:
            index = len(self._frames) - 1 - self._frames[::-1].index(tag)
            del self._frames[index:]

    def handle_data(self, data: str) -> None:
        """@brief Retain visible text, including tails outside paragraph elements."""
        if not self._ignored_tags:
            self._parts.append(data)

    def close(self) -> None:
        """@brief Drain the HTML parser before flushing the final visible text."""
        super().close()
        self._flush_block()

    def _flush_block(self) -> None:
        """@brief Collapse markup whitespace while preserving explicit line breaks and preformatted text."""
        tag = next((frame for frame in reversed(self._frames) if frame in self._BLOCK_KINDS), "body")
        kind = next(
            (
                self._BLOCK_KINDS[frame]
                for frame in reversed(self._frames)
                if frame in self._BLOCK_KINDS and self._BLOCK_KINDS[frame] != "body"
            ),
            "body",
        )
        if "pre" in self._frames:
            text = (
                "".join("\n" if part is None else part for part in self._parts)
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .strip("\n")
            )
        else:
            lines = [""]
            for part in self._parts:
                if part is None:
                    lines.append("")
                else:
                    lines[-1] += part
            text = "\n".join(" ".join(line.split()) for line in lines).strip()
        self._parts.clear()
        if text:
            self._append_event(text, kind, tag)

    def _append_event(self, text: str, kind: str, tag: str) -> None:
        self._block_index += 1
        self.events.append(
            SourceEvent(
                text=text,
                kind=kind,
                structure_origin="native",
                boundary_before="\n\n",
                boundary_kind="native_paragraph",
                locator={
                    "spine_index": self._spine_index,
                    "item_id": self._item_id,
                    "block_index": self._block_index,
                },
                native={"tag": tag, "heading_level": _heading_level(tag)},
            )
        )


def _heading_level(tag: str) -> int | None:
    """@brief Return a numeric heading level for h1-h6 tags."""
    normalized = str(tag).casefold()
    if len(normalized) == 2 and normalized[0] == "h" and normalized[1].isdigit():
        return int(normalized[1])
    return None


# END OF FILE
