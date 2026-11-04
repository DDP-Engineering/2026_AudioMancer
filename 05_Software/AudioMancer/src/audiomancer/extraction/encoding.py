#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file encoding.py
@brief Deterministic Unicode and declared encoding decoding.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

import codecs
from pathlib import Path
import re
import unicodedata

# PUBLIC API

_LEGACY_TEXT_ENCODINGS = ("cp1250", "cp1251", "cp1252")
_LEGACY_TIE_PRIORITY = {"cp1251": 0, "cp1250": 1, "cp1252": 2}
_CENTRAL_EUROPEAN_LETTERS = frozenset(
    "\u0104\u0105\u0106\u0107\u010c\u010d\u010e\u010f\u0110\u0111\u0118\u0119\u011a\u011b"
    "\u0139\u013a\u013d\u013e\u0141\u0142\u0143\u0144\u0147\u0148\u0150\u0151\u0154\u0155"
    "\u0158\u0159\u015a\u015b\u0160\u0161\u0164\u0165\u016e\u016f\u0170\u0171\u0179\u017a"
    "\u017b\u017c\u017d\u017e"
)
_WESTERN_EUROPEAN_LETTERS = frozenset(
    "\u00c0\u00c1\u00c2\u00c3\u00c4\u00c5\u00c6\u00c7\u00c8\u00c9\u00ca\u00cb"
    "\u00cc\u00cd\u00ce\u00cf\u00d0\u00d1\u00d2\u00d3\u00d4\u00d5\u00d6\u00d8"
    "\u00d9\u00da\u00db\u00dc\u00dd\u00de\u00df\u00e0\u00e1\u00e2\u00e3\u00e4"
    "\u00e5\u00e6\u00e7\u00e8\u00e9\u00ea\u00eb\u00ec\u00ed\u00ee\u00ef\u00f0"
    "\u00f1\u00f2\u00f3\u00f4\u00f5\u00f6\u00f8\u00f9\u00fa\u00fb\u00fc\u00fd"
    "\u00fe\u00ff"
)
_WESTERN_TYPOGRAPHY = frozenset("\u2018\u2019\u201c\u201d\u2013\u2014\u2026\u20ac\u0152\u0153\u0178")
_XML_ENCODING_PATTERN = re.compile(
    r"<\?xml\b[^>]*\bencoding\s*=\s*['\"]\s*([^'\"\s]+)",
    re.IGNORECASE,
)
_META_TAG_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_CHARSET_PATTERN = re.compile(r"\bcharset\s*=\s*['\"]?\s*([^\s'\"/>;]+)", re.IGNORECASE)
_META_ATTRIBUTE_PATTERN = re.compile(
    r"([^\s=/>]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.IGNORECASE,
)


def _read_text_with_fallback(path: Path) -> tuple[str, str]:
    """@brief Read one text source and report the selected encoding."""
    source_bytes = path.read_bytes()
    return _decode_bytes_with_fallback(source_bytes)


def _decode_bytes_with_fallback(source_bytes: bytes) -> tuple[str, str]:
    """@brief Decode text bytes by signature, strict UTF-8, or scored legacy evidence."""
    signature_encoding = _encoding_from_signature(source_bytes)
    if signature_encoding is not None:
        return source_bytes.decode(signature_encoding), _normalize_encoding_label(signature_encoding)

    try:
        return source_bytes.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    candidates: list[tuple[int, int, str, str]] = []
    for encoding in _LEGACY_TEXT_ENCODINGS:
        try:
            decoded = source_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        candidates.append(
            (
                _legacy_text_score(decoded, encoding),
                _LEGACY_TIE_PRIORITY[encoding],
                decoded,
                encoding,
            )
        )
    if candidates:
        _score, _priority, decoded, encoding = max(candidates, key=lambda candidate: candidate[:2])
        return decoded, encoding

    return source_bytes.decode("latin-1"), "latin-1"


def _decode_markup_bytes(source_bytes: bytes, *, context: str) -> tuple[str, str]:
    """
    @brief      Decode one XML/HTML content document using signatures and declarations.
    @param[in]  source_bytes Raw content-document bytes.
    @param[in]  context Spine item identity used in actionable errors.
    @return     Decoded text and normalized encoding label.
    @exception  ValueError A declaration is unknown or strict decoding fails.
    """
    signature_encoding = _encoding_from_signature(source_bytes)
    if signature_encoding is not None:
        try:
            decoded = source_bytes.decode(signature_encoding)
        except UnicodeDecodeError as error:
            raise ValueError(f"{context} cannot be decoded as {signature_encoding}: {error}") from error
        declared_encoding = _xml_declared_encoding(decoded)
        if declared_encoding is not None:
            _resolve_encoding_label(declared_encoding, context=context)
        return decoded, _normalize_encoding_label(signature_encoding)

    header_text = source_bytes[:4096].decode("latin-1")
    declared_encoding = _xml_declared_encoding(header_text) or _html_declared_encoding(header_text)
    if declared_encoding is not None:
        return _decode_declared_bytes(source_bytes, declared_encoding, context=context)
    return _decode_bytes_with_fallback(source_bytes)


def _decode_declared_bytes(
    source_bytes: bytes,
    declared_encoding: str,
    *,
    context: str,
) -> tuple[str, str]:
    """
    @brief      Strictly decode bytes with one explicit standard-library codec.
    @param[in]  source_bytes Raw source bytes.
    @param[in]  declared_encoding Encoding name read from the source format.
    @param[in]  context Source identity used in actionable errors.
    @return     Decoded text and normalized encoding label.
    @exception  ValueError The codec is unknown or strict decoding fails.
    """
    encoding = _resolve_encoding_label(declared_encoding, context=context)
    try:
        return source_bytes.decode(encoding), encoding
    except UnicodeDecodeError as error:
        raise ValueError(f"{context} cannot be decoded as declared {encoding}: {error}") from error


def _resolve_encoding_label(declared_encoding: str, *, context: str) -> str:
    """@brief Resolve one declared codec to its deterministic standard-library name."""
    try:
        return codecs.lookup(str(declared_encoding).strip()).name
    except LookupError as error:
        raise ValueError(f"{context} declares unsupported encoding '{declared_encoding}'.") from error


def _normalize_encoding_label(encoding: str) -> str:
    """@brief Return the standard-library canonical name for one known codec."""
    return codecs.lookup(encoding).name


def _encoding_from_signature(source_bytes: bytes) -> str | None:
    """@brief Return a BOM or XML byte-pattern encoding without inspecting text."""
    signatures = (
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF16_BE, "utf-16"),
        (codecs.BOM_UTF16_LE, "utf-16"),
    )
    for signature, encoding in signatures:
        if source_bytes.startswith(signature):
            return encoding
    if source_bytes.startswith(b"\x00\x00\x00<"):
        return "utf-32-be"
    if source_bytes.startswith(b"<\x00\x00\x00"):
        return "utf-32-le"
    if source_bytes.startswith(b"\x00<\x00?"):
        return "utf-16-be"
    if source_bytes.startswith(b"<\x00?\x00"):
        return "utf-16-le"
    return None


def _xml_declared_encoding(header_text: str) -> str | None:
    """@brief Return an XML declaration's encoding value when present."""
    match = _XML_ENCODING_PATTERN.search(header_text[:4096])
    return None if match is None else match.group(1)


def _html_declared_encoding(header_text: str) -> str | None:
    """@brief Return an applicable HTML meta charset from the document header."""
    for match in _META_TAG_PATTERN.finditer(header_text[:4096]):
        tag = match.group(0)
        attributes = {
            attribute_match.group(1).casefold(): next(
                value for value in attribute_match.groups()[1:] if value is not None
            )
            for attribute_match in _META_ATTRIBUTE_PATTERN.finditer(tag)
        }
        if attributes.get("charset"):
            return attributes["charset"]
        if attributes.get("http-equiv", "").casefold() != "content-type":
            continue
        charset_match = _META_CHARSET_PATTERN.search(attributes.get("content", ""))
        if charset_match is not None:
            return charset_match.group(1)
    return None


def _legacy_text_score(text: str, encoding: str) -> int:
    """
    @brief      Score one legacy decode by script coherence and text quality.
    @param[in]  text Candidate Unicode text.
    @param[in]  encoding Windows code page used for the candidate.
    @return     Comparable deterministic evidence score.
    @exception  None
    """
    letters = [character for character in text if unicodedata.category(character).startswith("L")]
    latin_count = sum("LATIN" in unicodedata.name(character, "") for character in letters)
    cyrillic_count = sum("CYRILLIC" in unicodedata.name(character, "") for character in letters)
    control_count = sum(
        unicodedata.category(character).startswith("C") and character not in "\t\r\n" for character in text
    )
    symbol_count = sum(unicodedata.category(character).startswith("S") for character in text)
    non_ascii_latin_count = sum(
        ord(character) > 127 and "LATIN" in unicodedata.name(character, "") for character in letters
    )
    score = (
        (2 * max(latin_count, cyrillic_count))
        - (12 * min(latin_count, cyrillic_count))
        - (40 * control_count)
        - (4 * symbol_count)
    )
    if latin_count and non_ascii_latin_count / latin_count > 0.65:
        score -= 5 * non_ascii_latin_count
    if encoding == "cp1251":
        score += 6 * cyrillic_count
    elif encoding == "cp1250":
        score += 4 * sum(character in _CENTRAL_EUROPEAN_LETTERS for character in text)
    elif encoding == "cp1252":
        score += 4 * sum(character in _WESTERN_EUROPEAN_LETTERS for character in text)
        score += 3 * sum(character in _WESTERN_TYPOGRAPHY for character in text)
    return score


def _summarize_epub_encodings(encodings: list[str]) -> str | None:
    """@brief Return a truthful uniform or deterministic mixed EPUB encoding token."""
    unique_encodings = sorted(set(encodings))
    if not unique_encodings:
        return None
    if len(unique_encodings) == 1:
        return unique_encodings[0]
    return f"mixed({','.join(unique_encodings)})"


# END OF FILE
