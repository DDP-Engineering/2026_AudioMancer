#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file fb2.py
@brief Extract FictionBook 2 bodies, structural text and auxiliary notes.
@details Parses XML without DTDs or entities and retains body order without following note links.
"""

# IMPORTS

from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from ..encoding import _decode_markup_bytes
from ..models import ExtractionAdapterResult, SourceEvent, _emit_adapter_progress, check_cancelled

# CONSTANTS

_NAMESPACE = "http://www.gribuser.ru/xml/fictionbook/2.0"
_PREFIX = "{" + _NAMESPACE + "}"
_PARAGRAPHS = frozenset(("p", "subtitle", "text-author", "date", "v"))
_CONTAINERS = frozenset(("body", "section", "title", "epigraph", "cite", "poem", "annotation"))

# PUBLIC API


def _extract_fb2(source_path: Path, *, progress_callback=None, cancel_requested=None) -> ExtractionAdapterResult:
    """
    @brief Extract body content while excluding publication metadata and binary image payloads.
    @param[in] source_path Uncompressed FictionBook XML source.
    @param[in] progress_callback Optional current/total/message observer.
    @param[in] cancel_requested Cooperative cancellation predicate.
    @return Structural units and diagnostics for auxiliary or unsupported body elements.
    @exception ValueError The source is malformed, unsafe or not a readable FictionBook 2 document.
    """
    check_cancelled(cancel_requested)
    content, encoding = _decode_markup_bytes(source_path.read_bytes(), context=f"FB2 source '{source_path.name}'")
    try:
        root = fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException) as error:
        raise ValueError(f"FB2 source '{source_path.name}' contains invalid or prohibited XML: {error}") from error
    if root.tag != _PREFIX + "FictionBook":
        raise ValueError("FB2 source must have a FictionBook root in the FictionBook 2 namespace.")
    bodies = root.findall(_PREFIX + "body")
    if not bodies:
        raise ValueError("FB2 source does not contain a book body.")
    events: list[SourceEvent] = []
    warnings: list[str] = []
    total = max(1, sum(1 for body in bodies for _node in body.iter()))
    reasons: set[str] = set()
    processed = 0
    for body_index, body in enumerate(bodies):
        body_name = body.get("name")
        if body_index:
            warnings.append(
                f"FB2 auxiliary body {body_name or body_index!r} was kept after the main body; review notes placement."
            )
        stack = [(body, 0, "footnote" if body_index else "body", f"body[{body_index}]")]
        while stack:
            check_cancelled(cancel_requested)
            node, depth, role, path = stack.pop()
            processed += 1
            tag = _local_name(node)
            if not tag:
                raise ValueError(f"FB2 body contains an unsupported foreign element: {node.tag}")
            if tag == "section":
                depth += 1
            elif tag == "title":
                role = "heading"
            elif tag in {"epigraph", "cite"} and role != "footnote":
                role = "blockquote"
            text = None
            boundary = "\n\n"
            kind = role
            if tag in _PARAGRAPHS:
                text = _inline_text(node)
                if tag == "subtitle":
                    kind = "heading"
                elif tag == "v":
                    kind = "verse"
            elif tag == "stanza":
                text = "\n".join(_inline_text(line) for line in node if _local_name(line) == "v")
                kind = "verse"
            elif tag == "tr":
                text = "\t".join(_inline_text(cell) for cell in node if _local_name(cell) in {"td", "th"})
                kind = "table_or_preformatted"
                boundary = "\n"
            elif tag in {"image", "empty-line", "binary"}:
                text = ""
            elif tag not in _CONTAINERS and tag != "table" and (node.text or "").strip():
                text = _inline_text(node)
                reasons.add("unrecognized_fb2_element")
                warnings.append(f"FB2 element {tag!r} was retained as plain text; review its structure.")
            if text:
                events.append(
                    SourceEvent(
                        text=text,
                        kind=kind,
                        structure_origin="native",
                        boundary_before=boundary,
                        boundary_kind="table_row" if tag == "tr" else "native_paragraph",
                        locator={"body_index": body_index, "element_path": path, "element_id": node.get("id")},
                        native={
                            "tag": tag,
                            "body_name": body_name,
                            "heading_level": min(6, depth + 1) if kind == "heading" else None,
                        },
                    )
                )
            if text is None:
                for index, child in reversed(list(enumerate(node))):
                    stack.append((child, depth, role, f"{path}/{_local_name(child) or 'foreign'}[{index}]"))
            _emit_adapter_progress(progress_callback, processed, total, f"FB2 body {body_index + 1} parsed.")
    if not events:
        raise ValueError("FB2 source did not contain readable body text.")
    _emit_adapter_progress(progress_callback, total, total, "FB2 document parsed.")
    return ExtractionAdapterResult(
        events=events,
        warnings=warnings,
        pages=[],
        structure_quality="native_partial" if reasons else "native",
        eligibility_mode="native_partial" if reasons else "native",
        eligibility_reason_codes=sorted(reasons),
        encoding=encoding,
        progress_total=total,
        page_count=None,
    )


# LOCAL HELPERS


def _local_name(node) -> str:
    """@brief Accept only elements in the FictionBook 2 namespace."""
    return node.tag[len(_PREFIX) :] if isinstance(node.tag, str) and node.tag.startswith(_PREFIX) else ""


def _inline_text(node) -> str:
    """@brief Preserve mixed inline text and tails while collapsing source-format whitespace."""
    return " ".join("".join(node.itertext()).split())


# END OF FILE
