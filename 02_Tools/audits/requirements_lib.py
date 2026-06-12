#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file requirements_lib.py
@brief Shared parser for AudioMancer requirement register tables.
@details Reads the Markdown requirement registers under `0_Planning/Requirements/`
         into structured records so traceability, coverage, and impact tools can
         share one source of truth for register parsing and test-node discovery.
@author Eng. Dan Dumitru Pasare
@date 2026-06-09
@version 0.2.0
"""

# IMPORTS

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# CONSTANTS

REGISTER_DIR = Path("0_Planning/Requirements")
REGISTER_README = "README.md"
REQUIREMENT_ID_PREFIX = "REQ-AUDIO"
APP_DIR = Path("04_Software/AudioMancer")
TESTS_DIR = Path("tests")
TEST_FILE_PREFIX = "test_"
TEST_FUNCTION_PREFIX = "test"
TEST_CLASS_PREFIX = "Test"
CELL_LIST_SEPARATOR = ";"
NOT_APPLICABLE = "N/A"
EXPECTED_COLUMN_COUNT = 10

# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class Requirement:
    """
    @brief      One parsed requirement register row.
    @param[in]  id Stable requirement identifier.
    @param[in]  status Lifecycle status such as Active, Planned, or Retired.
    @param[in]  priority Must, Should, or Could.
    @param[in]  requirement Verifiable requirement statement.
    @param[in]  rationale Reason the requirement exists.
    @param[in]  related_components Repository-relative component paths.
    @param[in]  verification_method Verification approach text.
    @param[in]  linked_tests Resolvable pytest node identifiers.
    @param[in]  created_on Creation timestamp string.
    @param[in]  last_updated Last material change timestamp string.
    @param[in]  source_file Repository-relative register file path.
    @param[in]  line One-based source line for the row.
    @return     Immutable requirement record.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """

    id: str
    status: str
    priority: str
    requirement: str
    rationale: str
    related_components: tuple[str, ...]
    verification_method: str
    linked_tests: tuple[str, ...]
    created_on: str
    last_updated: str
    source_file: Path
    line: int

    @property
    def is_active(self) -> bool:
        """
        @brief      Report whether the requirement is in the Active lifecycle.
        @return     True when the status equals Active, case-insensitively.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    0.1.0
        """
        return self.status.strip().casefold() == "active"

    @property
    def has_manual_verification(self) -> bool:
        """
        @brief      Report whether the row names a manual verification method.
        @return     True when the verification text references a manual method.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-09
        @version    0.1.0
        """
        text = self.verification_method.casefold()
        return any(token in text for token in ("manual", "inspection", "review"))


# PUBLIC API


def _split_cell_list(cell: str) -> tuple[str, ...]:
    """
    @brief      Split a semicolon-delimited register cell into clean values.
    @param[in]  cell Raw Markdown cell text.
    @return     Ordered values with backticks, spaces, and N/A removed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    values: list[str] = []
    for raw in cell.split(CELL_LIST_SEPARATOR):
        value = raw.strip().strip("`").strip()
        if not value or value == NOT_APPLICABLE:
            continue
        values.append(value)
    return tuple(values)


def _parse_row(line: str) -> list[str] | None:
    """
    @brief      Parse one Markdown table line into trimmed cell values.
    @param[in]  line Raw register table line.
    @return     Cell value list for a requirement row, otherwise None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not cells or not cells[0].startswith(REQUIREMENT_ID_PREFIX):
        return None
    return cells


def parse_register_file(path: Path, source: Path | None = None) -> list[Requirement]:
    """
    @brief      Parse one requirement register Markdown file.
    @param[in]  path Absolute path to the register file.
    @param[in]  source Optional repository-relative path for reporting.
    @return     Parsed requirement records for the file.
    @exception  ValueError Raised when a requirement row has the wrong shape.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    source_path = source if source is not None else path
    requirements: list[Requirement] = []
    text = path.read_text(encoding="utf-8")
    for index, line in enumerate(text.splitlines(), start=1):
        cells = _parse_row(line)
        if cells is None:
            continue
        if len(cells) != EXPECTED_COLUMN_COUNT:
            raise ValueError(
                f"{source_path}:{index} expected {EXPECTED_COLUMN_COUNT} "
                f"columns, found {len(cells)}."
            )
        requirements.append(
            Requirement(
                id=cells[0],
                status=cells[1],
                priority=cells[2],
                requirement=cells[3],
                rationale=cells[4],
                related_components=_split_cell_list(cells[5]),
                verification_method=cells[6],
                linked_tests=_split_cell_list(cells[7]),
                created_on=cells[8],
                last_updated=cells[9],
                source_file=source_path,
                line=index,
            )
        )
    return requirements


def register_files(root: Path) -> list[Path]:
    """
    @brief      Resolve repository-relative requirement register files.
    @param[in]  root Repository root path.
    @return     Ordered register file paths excluding the folder README.
    @exception  RuntimeError Raised when the register directory is missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    register_root = root / REGISTER_DIR
    if not register_root.is_dir():
        raise RuntimeError(f"Requirement register directory not found: {REGISTER_DIR}.")
    files = [
        path
        for path in sorted(register_root.glob("*.md"))
        if path.name != REGISTER_README
    ]
    return [path.relative_to(root) for path in files]


def load_requirements(root: Path) -> list[Requirement]:
    """
    @brief      Load every requirement from the register directory.
    @param[in]  root Repository root path.
    @return     Parsed requirement records across all register files.
    @exception  RuntimeError Raised when the register directory is missing.
    @exception  ValueError Raised when a requirement row has the wrong shape.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    requirements: list[Requirement] = []
    for source in register_files(root):
        requirements.extend(parse_register_file(root / source, source=source))
    return requirements


def linked_test_file(node_id: str) -> str:
    """
    @brief      Resolve the test file portion of a pytest node identifier.
    @param[in]  node_id Linked pytest node identifier.
    @return     Test file path without the node selector suffix.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    return node_id.split("::", maxsplit=1)[0]


def collect_defined_test_nodes(app_dir: Path) -> set[str]:
    """
    @brief      Collect pytest-style test node identifiers by static analysis.
    @details    Parses every `test_*.py` file under the application `tests/`
                directory with `ast` and yields `tests/<file>::<test>` for each
                module-level test function and `Test*` class method, without
                importing test modules or running pytest collection.
    @param[in]  app_dir Absolute path to the AudioMancer application directory.
    @return     Set of statically defined test node identifiers.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    tests_root = app_dir / TESTS_DIR
    nodes: set[str] = set()
    if not tests_root.is_dir():
        return nodes
    for path in sorted(tests_root.rglob(f"{TEST_FILE_PREFIX}*.py")):
        relative = path.relative_to(app_dir).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for item in tree.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                if item.name.startswith(TEST_FUNCTION_PREFIX):
                    nodes.add(f"{relative}::{item.name}")
            elif isinstance(item, ast.ClassDef) and item.name.startswith(TEST_CLASS_PREFIX):
                for member in item.body:
                    if (
                        isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
                        and member.name.startswith(TEST_FUNCTION_PREFIX)
                    ):
                        nodes.add(f"{relative}::{item.name}::{member.name}")
                        nodes.add(f"{relative}::{member.name}")
    return nodes


# END OF FILE
