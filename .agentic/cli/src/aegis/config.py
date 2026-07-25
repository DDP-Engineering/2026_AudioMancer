#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file config.py
@brief Strict schema-version-2 workflow configuration parser.
@details Treats `.agentic/workflow.toml` as the only repository-policy source,
         validates it deterministically, and exposes immutable typed records.
         Missing, malformed, incomplete, and inconsistent configuration is an
         actionable error; no repository paths, patterns, or modes are inferred.
@author Eng. Dan Dumitru Pasare
@date 2026-07-22
@version 1.0.2
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, NoReturn
import tomllib

from .models import ALL_STAGES

# CONSTANTS

SCHEMA_VERSION = 2
CONFIG_RELATIVE_PATH = Path(".agentic") / "workflow.toml"
RISK_LEVELS = ("low", "medium", "high")
COMPLETION_LEVELS = (
    "unknown",
    "discovered",
    "characterized",
    "baseline-usable",
    "baseline-strict",
)

_TOP_LEVEL_KEYS = (
    "schema_version",
    "source",
    "tests",
    "requirements",
    "documentation",
    "components",
    "knowledge",
    "reports",
    "traceability",
    "adoption",
    "alignment",
    "gates",
    "guardrails",
)

# DATA MODELS / TYPEDEFINITIONS


class ConfigurationError(ValueError):
    """
    @brief Typed actionable workflow configuration failure.
    @param[in] code Stable machine-readable configuration error code.
    @param[in] config_path Configuration file associated with the failure.
    @param[in] key_path Dotted TOML key path, or an empty string for the file.
    @param[in] received Value received from the document.
    @param[in] expected Human-readable expected value or shape.
    @param[in] message Concise description of the failure.
    @param[in] remediation Concrete repair instruction for an agent or operator.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 0.1.0
    """

    def __init__(
        self,
        *,
        code: str,
        config_path: Path,
        key_path: str,
        received: object,
        expected: object,
        message: str,
        remediation: str,
    ) -> None:
        """
        @brief      Store one configuration error without losing JSON fields.
        @param[in]  code Stable error code.
        @param[in]  config_path Configuration file path.
        @param[in]  key_path Dotted TOML key path.
        @param[in]  received Rejected value.
        @param[in]  expected Expected value or shape.
        @param[in]  message Failure description.
        @param[in]  remediation Concrete repair instruction.
        @return     None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-22
        @version    0.1.0
        """
        super().__init__(message)
        self.code = code
        self.config_path = config_path
        self.key_path = key_path
        self.received = received
        self.expected = expected
        self.message = message
        self.remediation = remediation

    def __str__(self) -> str:
        """
        @brief      Render the stable text error contract.
        @return     Error code and message followed by remediation.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-22
        @version    0.1.0
        """
        return f"{self.code}: {self.message}\n{self.remediation}"

    def to_dict(self) -> dict[str, object]:
        """
        @brief      Serialize the error for JSON-capable callers.
        @return     Stable configuration-error field mapping.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-22
        @version    0.1.0
        """
        return {
            "code": self.code,
            "config_path": self.config_path.as_posix(),
            "key_path": self.key_path,
            "received": self.received,
            "expected": self.expected,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class RuleSetPolicy:
    """@brief Immutable mode and regex/glob rule collection."""

    mode: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ProtectedPathPolicy:
    """@brief Immutable protected-path policy and covered operations."""

    mode: str
    patterns: tuple[str, ...]
    operations: tuple[str, ...]


@dataclass(frozen=True)
class WorkingTreePolicy:
    """@brief Immutable working-tree blocker policy."""

    mode: str
    blocked_patterns: tuple[str, ...]


@dataclass(frozen=True)
class WriteAccessPolicy:
    """@brief Immutable write-access mode and complete stage mapping."""

    mode: str
    stages: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class ScopePolicy:
    """@brief Immutable scope-checking policy."""

    mode: str
    allowed_roots: tuple[str, ...]


@dataclass(frozen=True)
class CoveragePolicy:
    """@brief Immutable requirement-coverage policy."""

    mode: str
    coverable_roots: tuple[str, ...]
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class GatePolicy:
    """@brief Immutable validation-gate policy."""

    mode: str
    test: tuple[str, ...]
    lint: tuple[str, ...]


@dataclass(frozen=True)
class BaselineGuardPolicy:
    """@brief Immutable component baseline guard policy."""

    mode: str
    minimum_completion_level: str | None


@dataclass(frozen=True)
class SourceChangePolicy:
    """@brief Immutable adoption source-change policy."""

    mode: str


@dataclass(frozen=True)
class DeliveryPolicy:
    """@brief Immutable outward-delivery preflight hook policy."""

    mode: str
    command_patterns: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowConfig:
    """
    @brief Complete immutable schema-version-2 workflow configuration.
    @details Every field is required from the validated TOML document. The
             compatibility properties expose legacy flat consumer names while
             sourcing their values exclusively from explicit policy records.
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-22
    @version 1.0.0
    """

    schema_version: int
    source_roots: tuple[str, ...]
    test_roots: tuple[str, ...]
    requirement_roots: tuple[str, ...]
    documentation_roots: tuple[str, ...]
    component_documentation_template: str
    component_manifest: str
    component_baseline_guard: BaselineGuardPolicy
    knowledge_roots: tuple[str, ...]
    adoption_report_root: str
    traceability_language: str
    source_extensions: tuple[str, ...]
    test_file_patterns: tuple[str, ...]
    coverage: CoveragePolicy
    adoption_allow_component_bundles: bool
    adoption_max_bundle_components: int
    adoption_source_changes: SourceChangePolicy
    alignment_enabled: bool
    alignment_pause_on_open_questions: bool
    alignment_risk_threshold: str
    alignment_allow_recommended_responses: bool
    alignment_protected_scope: RuleSetPolicy
    gates: GatePolicy
    secrets: RuleSetPolicy
    protected_paths: ProtectedPathPolicy
    working_tree: WorkingTreePolicy
    write_access: WriteAccessPolicy
    scope: ScopePolicy
    delivery: DeliveryPolicy

    @property
    def coverable_roots(self) -> tuple[str, ...]:
        """@brief Return explicitly configured coverage roots."""
        return self.coverage.coverable_roots

    @property
    def coverable_exclude(self) -> tuple[str, ...]:
        """@brief Return explicitly configured coverage exclusions."""
        return self.coverage.exclude

    @property
    def gate_commands(self) -> Mapping[str, tuple[str, ...]]:
        """
        @brief      Return gate groups only when gate execution is enforced.
        @return     Immutable configured gate groups or an empty mapping.
        @version    1.0.1
        """
        if self.gates.mode == "disabled":
            return MappingProxyType({})
        return MappingProxyType({"test": self.gates.test, "lint": self.gates.lint})

    @property
    def secret_patterns(self) -> tuple[str, ...]:
        """@brief Return explicitly configured secret patterns."""
        return self.secrets.patterns

    @property
    def working_tree_blocked_patterns(self) -> tuple[str, ...]:
        """@brief Return explicitly configured working-tree patterns."""
        return self.working_tree.blocked_patterns

    @property
    def write_zones(self) -> Mapping[str, tuple[str, ...]]:
        """@brief Return explicitly configured stage write zones."""
        return self.write_access.stages

    @property
    def alignment_protected_scope_patterns(self) -> tuple[str, ...]:
        """@brief Return explicitly configured protected alignment patterns."""
        return self.alignment_protected_scope.patterns

    @property
    def adoption_behavior_changes_allowed(self) -> bool:
        """@brief Report whether adoption source changes are unrestricted."""
        return self.adoption_source_changes.mode == "unrestricted"

    @property
    def adoption_default_completion_level(self) -> str | None:
        """@brief Return the enforced baseline threshold, when enabled."""
        return self.component_baseline_guard.minimum_completion_level


# HELPER FUNCTIONS


class _Parser:
    """@brief Deterministic schema-version-2 document parser."""

    def __init__(self, repo_root: Path, path: Path, data: dict[str, Any]) -> None:
        self.repo_root = repo_root
        self.path = path
        self.data = data

    def parse(self) -> WorkflowConfig:
        """@brief Validate the complete document and build its immutable model."""
        self._closed(self.data, "", _TOP_LEVEL_KEYS)
        self._schema_version()

        source = self._table(self.data, "source", "source", ("roots",))
        source_roots = self._paths(source, "roots", "source.roots", non_empty=True)

        tests = self._table(self.data, "tests", "tests", ("roots",))
        test_roots = self._paths(tests, "roots", "tests.roots", non_empty=True)

        requirements = self._table(
            self.data, "requirements", "requirements", ("roots",)
        )
        requirement_roots = self._paths(
            requirements, "roots", "requirements.roots", non_empty=True
        )

        documentation = self._table(
            self.data,
            "documentation",
            "documentation",
            ("roots", "component_template"),
        )
        documentation_roots = self._paths(
            documentation, "roots", "documentation.roots", non_empty=True
        )
        component_template = self._path(
            documentation,
            "component_template",
            "documentation.component_template",
        )

        components = self._table(
            self.data,
            "components",
            "components",
            ("manifest", "baseline_guard"),
        )
        component_manifest = self._path(components, "manifest", "components.manifest")
        baseline = self._baseline_guard(components, component_manifest)

        knowledge = self._table(self.data, "knowledge", "knowledge", ("roots",))
        knowledge_roots = self._paths(
            knowledge, "roots", "knowledge.roots", non_empty=True
        )

        reports = self._table(
            self.data, "reports", "reports", ("adoption_root",)
        )
        adoption_report_root = self._path(
            reports, "adoption_root", "reports.adoption_root"
        )

        traceability = self._table(
            self.data,
            "traceability",
            "traceability",
            ("language", "source_extensions", "test_file_patterns", "coverage"),
        )
        language = self._string(traceability, "language", "traceability.language")
        source_extensions = self._strings(
            traceability,
            "source_extensions",
            "traceability.source_extensions",
            non_empty=True,
        )
        test_file_patterns = self._globs(
            traceability,
            "test_file_patterns",
            "traceability.test_file_patterns",
            non_empty=True,
        )
        coverage = self._coverage(traceability)

        adoption = self._table(
            self.data,
            "adoption",
            "adoption",
            ("allow_component_bundles", "max_bundle_components", "source_changes"),
        )
        allow_bundles = self._boolean(
            adoption, "allow_component_bundles", "adoption.allow_component_bundles"
        )
        max_bundle_components = self._integer(
            adoption, "max_bundle_components", "adoption.max_bundle_components"
        )
        if max_bundle_components <= 0:
            self._fail(
                "CONFIG-RULE-INVALID",
                "adoption.max_bundle_components",
                max_bundle_components,
                "an integer greater than zero",
                "[adoption].max_bundle_components must be greater than zero.",
            )
        source_changes = self._source_changes(adoption)

        alignment = self._table(
            self.data,
            "alignment",
            "alignment",
            (
                "enabled",
                "pause_on_open_questions",
                "risk_threshold",
                "allow_recommended_responses",
                "protected_scope",
            ),
        )
        alignment_enabled = self._boolean(alignment, "enabled", "alignment.enabled")
        pause_on_questions = self._boolean(
            alignment,
            "pause_on_open_questions",
            "alignment.pause_on_open_questions",
        )
        risk_threshold = self._choice(
            alignment,
            "risk_threshold",
            "alignment.risk_threshold",
            RISK_LEVELS,
            "CONFIG-RULE-INVALID",
        )
        recommended_responses = self._boolean(
            alignment,
            "allow_recommended_responses",
            "alignment.allow_recommended_responses",
        )
        protected_scope = self._alignment_scope(alignment, alignment_enabled)

        gates = self._gate_policy()
        guardrails = self._table(
            self.data,
            "guardrails",
            "guardrails",
            (
                "secrets",
                "protected_paths",
                "working_tree",
                "write_access",
                "scope",
                "delivery",
            ),
        )
        secrets = self._rule_policy(
            guardrails,
            "secrets",
            "guardrails.secrets",
            ("disabled", "enforce"),
            regex=True,
        )
        protected_paths = self._protected_paths(guardrails)
        working_tree = self._working_tree(guardrails)
        write_access = self._write_access(guardrails)
        scope = self._scope(guardrails)
        delivery = self._delivery(guardrails)

        return WorkflowConfig(
            schema_version=SCHEMA_VERSION,
            source_roots=source_roots,
            test_roots=test_roots,
            requirement_roots=requirement_roots,
            documentation_roots=documentation_roots,
            component_documentation_template=component_template,
            component_manifest=component_manifest,
            component_baseline_guard=baseline,
            knowledge_roots=knowledge_roots,
            adoption_report_root=adoption_report_root,
            traceability_language=language,
            source_extensions=source_extensions,
            test_file_patterns=test_file_patterns,
            coverage=coverage,
            adoption_allow_component_bundles=allow_bundles,
            adoption_max_bundle_components=max_bundle_components,
            adoption_source_changes=source_changes,
            alignment_enabled=alignment_enabled,
            alignment_pause_on_open_questions=pause_on_questions,
            alignment_risk_threshold=risk_threshold,
            alignment_allow_recommended_responses=recommended_responses,
            alignment_protected_scope=protected_scope,
            gates=gates,
            secrets=secrets,
            protected_paths=protected_paths,
            working_tree=working_tree,
            write_access=write_access,
            scope=scope,
            delivery=delivery,
        )

    def _schema_version(self) -> None:
        value = self.data.get("schema_version")
        if type(value) is not int or value != SCHEMA_VERSION:
            self._fail(
                "CONFIG-SCHEMA-UNSUPPORTED",
                "schema_version",
                value,
                SCHEMA_VERSION,
                "schema_version is missing, has the wrong type, or is unsupported.",
                'Set `schema_version = 2` at the top of .agentic/workflow.toml.',
            )

    def _baseline_guard(
        self, components: dict[str, Any], manifest: str
    ) -> BaselineGuardPolicy:
        table = self._table(
            components,
            "baseline_guard",
            "components.baseline_guard",
            ("mode", "minimum_completion_level"),
            conditional=("minimum_completion_level",),
        )
        mode = self._choice(
            table,
            "mode",
            "components.baseline_guard.mode",
            ("disabled", "enforce"),
        )
        minimum = table.get("minimum_completion_level")
        if mode == "disabled":
            if "minimum_completion_level" in table:
                self._inconsistent(
                    "components.baseline_guard.minimum_completion_level",
                    minimum,
                    "omit the key when mode is disabled",
                )
            return BaselineGuardPolicy(mode, None)
        if "minimum_completion_level" not in table:
            self._missing_key(
                "components.baseline_guard.minimum_completion_level",
                f'Add `minimum_completion_level = "{COMPLETION_LEVELS[3]}"`.',
            )
        minimum = self._choice(
            table,
            "minimum_completion_level",
            "components.baseline_guard.minimum_completion_level",
            COMPLETION_LEVELS,
            "CONFIG-RULE-INVALID",
        )
        manifest_path = (self.repo_root / manifest).resolve()
        try:
            manifest_path.relative_to(self.repo_root.resolve())
        except ValueError:
            self._rule_invalid(
                "components.manifest", manifest, "a repository-relative manifest path"
            )
        if not manifest_path.is_file():
            self._rule_invalid(
                "components.manifest",
                manifest,
                "a readable component manifest when baseline_guard is enforced",
            )
        try:
            parsed = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            self._rule_invalid(
                "components.manifest", manifest, "a valid readable TOML manifest"
            )
        if not isinstance(parsed, dict):
            self._rule_invalid("components.manifest", manifest, "a TOML table document")
        return BaselineGuardPolicy(mode, minimum)

    def _coverage(self, traceability: dict[str, Any]) -> CoveragePolicy:
        table = self._table(
            traceability,
            "coverage",
            "traceability.coverage",
            ("mode", "coverable_roots", "exclude"),
        )
        mode = self._choice(
            table, "mode", "traceability.coverage.mode", ("disabled", "enforce")
        )
        roots = self._paths(
            table,
            "coverable_roots",
            "traceability.coverage.coverable_roots",
            non_empty=False,
        )
        exclude = self._globs(
            table, "exclude", "traceability.coverage.exclude", non_empty=False
        )
        if mode == "disabled" and (roots or exclude):
            self._inconsistent(
                "traceability.coverage",
                {"coverable_roots": list(roots), "exclude": list(exclude)},
                "empty coverable_roots and exclude lists in disabled mode",
            )
        if mode == "enforce" and not roots:
            self._inconsistent(
                "traceability.coverage.coverable_roots",
                [],
                "at least one root in enforce mode",
            )
        return CoveragePolicy(mode, roots, exclude)

    def _source_changes(self, adoption: dict[str, Any]) -> SourceChangePolicy:
        table = self._table(
            adoption, "source_changes", "adoption.source_changes", ("mode",)
        )
        mode = self._choice(
            table,
            "mode",
            "adoption.source_changes.mode",
            ("unrestricted", "blocked"),
        )
        return SourceChangePolicy(mode)

    def _alignment_scope(
        self, alignment: dict[str, Any], alignment_enabled: bool
    ) -> RuleSetPolicy:
        policy = self._rule_policy(
            alignment,
            "protected_scope",
            "alignment.protected_scope",
            ("disabled", "enforce"),
            regex=False,
        )
        if policy.mode == "enforce" and not alignment_enabled:
            self._inconsistent(
                "alignment.protected_scope.mode",
                "enforce",
                "mode = disabled when alignment.enabled is false",
            )
        return policy

    def _gate_policy(self) -> GatePolicy:
        table = self._table(
            self.data, "gates", "gates", ("mode", "test", "lint")
        )
        mode = self._choice(table, "mode", "gates.mode", ("disabled", "enforce"))
        test = self._commands(table, "test", "gates.test")
        lint = self._commands(table, "lint", "gates.lint")
        if mode == "disabled" and (test or lint):
            self._inconsistent(
                "gates", {"test": list(test), "lint": list(lint)}, "empty command lists"
            )
        if mode == "enforce" and not (test or lint):
            self._inconsistent(
                "gates", {"test": [], "lint": []}, "at least one configured command"
            )
        return GatePolicy(mode, test, lint)

    def _rule_policy(
        self,
        parent: dict[str, Any],
        key: str,
        key_path: str,
        modes: tuple[str, ...],
        *,
        regex: bool,
    ) -> RuleSetPolicy:
        table = self._table(parent, key, key_path, ("mode", "patterns"))
        mode = self._choice(table, "mode", f"{key_path}.mode", modes)
        patterns = (
            self._regexes(table, "patterns", f"{key_path}.patterns")
            if regex
            else self._globs(table, "patterns", f"{key_path}.patterns", non_empty=False)
        )
        self._rules_match_mode(key_path, mode, patterns)
        return RuleSetPolicy(mode, patterns)

    def _protected_paths(self, guardrails: dict[str, Any]) -> ProtectedPathPolicy:
        key_path = "guardrails.protected_paths"
        table = self._table(
            guardrails,
            "protected_paths",
            key_path,
            ("mode", "patterns", "operations"),
        )
        mode = self._choice(
            table, "mode", f"{key_path}.mode", ("disabled", "enforce")
        )
        patterns = self._globs(
            table, "patterns", f"{key_path}.patterns", non_empty=False
        )
        operations = self._choices(
            table,
            "operations",
            f"{key_path}.operations",
            ("read", "write"),
        )
        if mode == "disabled" and (patterns or operations):
            self._inconsistent(
                key_path,
                {"patterns": list(patterns), "operations": list(operations)},
                "empty patterns and operations lists in disabled mode",
            )
        if mode == "enforce" and (not patterns or not operations):
            self._inconsistent(
                key_path,
                {"patterns": list(patterns), "operations": list(operations)},
                "non-empty patterns and operations lists in enforce mode",
            )
        return ProtectedPathPolicy(mode, patterns, operations)

    def _working_tree(self, guardrails: dict[str, Any]) -> WorkingTreePolicy:
        key_path = "guardrails.working_tree"
        table = self._table(
            guardrails, "working_tree", key_path, ("mode", "blocked_patterns")
        )
        mode = self._choice(
            table, "mode", f"{key_path}.mode", ("unrestricted", "restricted")
        )
        patterns = self._globs(
            table,
            "blocked_patterns",
            f"{key_path}.blocked_patterns",
            non_empty=False,
        )
        self._rules_match_mode(key_path, mode, patterns)
        return WorkingTreePolicy(mode, patterns)

    def _write_access(self, guardrails: dict[str, Any]) -> WriteAccessPolicy:
        key_path = "guardrails.write_access"
        table = self._table(
            guardrails,
            "write_access",
            key_path,
            ("mode", "stages"),
            conditional=("stages",),
        )
        mode = self._choice(
            table, "mode", f"{key_path}.mode", ("unrestricted", "stage_restricted")
        )
        if mode == "unrestricted":
            if "stages" in table:
                self._inconsistent(
                    f"{key_path}.stages",
                    table["stages"],
                    "omit the stages table in unrestricted mode",
                )
            return WriteAccessPolicy(mode, MappingProxyType({}))
        if "stages" not in table:
            self._missing_key(
                f"{key_path}.stages",
                "Add every supported stage below [guardrails.write_access.stages].",
            )
        stages = table["stages"]
        if not isinstance(stages, dict):
            self._type_invalid(f"{key_path}.stages", stages, "a TOML table")
        self._closed(stages, f"{key_path}.stages", tuple(ALL_STAGES))
        parsed: dict[str, tuple[str, ...]] = {}
        for stage in ALL_STAGES:
            if stage not in stages:
                self._missing_key(
                    f"{key_path}.stages.{stage}",
                    f"Add `{stage} = []` or an explicit list of repository globs.",
                )
            parsed[stage] = self._globs(
                stages,
                stage,
                f"{key_path}.stages.{stage}",
                non_empty=False,
            )
        return WriteAccessPolicy(mode, MappingProxyType(parsed))

    def _scope(self, guardrails: dict[str, Any]) -> ScopePolicy:
        key_path = "guardrails.scope"
        table = self._table(guardrails, "scope", key_path, ("mode", "allowed_roots"))
        mode = self._choice(
            table,
            "mode",
            f"{key_path}.mode",
            ("unrestricted", "advisory", "enforce"),
        )
        roots = self._paths(
            table, "allowed_roots", f"{key_path}.allowed_roots", non_empty=False
        )
        if mode == "unrestricted" and roots:
            self._inconsistent(
                f"{key_path}.allowed_roots", list(roots), "an empty list in unrestricted mode"
            )
        if mode != "unrestricted" and not roots:
            self._inconsistent(
                f"{key_path}.allowed_roots", [], f"at least one root in {mode} mode"
            )
        return ScopePolicy(mode, roots)

    def _delivery(self, guardrails: dict[str, Any]) -> DeliveryPolicy:
        key_path = "guardrails.delivery"
        table = self._table(
            guardrails, "delivery", key_path, ("mode", "command_patterns")
        )
        mode = self._choice(
            table, "mode", f"{key_path}.mode", ("disabled", "enforce")
        )
        raw = self._strings(
            table,
            "command_patterns",
            f"{key_path}.command_patterns",
            non_empty=False,
        )
        patterns: list[str] = []
        for value in raw:
            normalized = " ".join(value.lower().split())
            if normalized in patterns:
                self._rule_invalid(
                    f"{key_path}.command_patterns", value, "unique normalized command fragments"
                )
            patterns.append(normalized)
        result = tuple(patterns)
        self._rules_match_mode(key_path, mode, result)
        return DeliveryPolicy(mode, result)

    def _rules_match_mode(
        self, key_path: str, mode: str, rules: tuple[str, ...]
    ) -> None:
        unrestricted = mode in {"disabled", "unrestricted"}
        if unrestricted and rules:
            self._inconsistent(key_path, list(rules), f"an empty rule list in {mode} mode")
        if not unrestricted and not rules:
            self._inconsistent(key_path, [], f"at least one rule in {mode} mode")

    def _table(
        self,
        parent: dict[str, Any],
        key: str,
        key_path: str,
        keys: tuple[str, ...],
        *,
        conditional: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if key not in parent:
            self._fail(
                "CONFIG-SECTION-MISSING",
                key_path,
                None,
                "a TOML table",
                f"Required configuration table [{key_path}] is missing.",
                f"Add the complete [{key_path}] table, then run `aegis config validate`.",
            )
        value = parent[key]
        if not isinstance(value, dict):
            self._type_invalid(key_path, value, "a TOML table")
        self._closed(value, key_path, keys)
        for required in keys:
            if required in conditional:
                continue
            if required not in value:
                self._missing_key(
                    f"{key_path}.{required}",
                    f"Add `{required}` to [{key_path}], then run `aegis config validate`.",
                )
        return value

    def _closed(
        self, table: dict[str, Any], key_path: str, allowed: tuple[str, ...]
    ) -> None:
        unknown = [key for key in table if key not in allowed]
        if unknown:
            full = f"{key_path}.{unknown[0]}" if key_path else unknown[0]
            self._type_invalid(full, table[unknown[0]], f"one of: {', '.join(allowed)}")

    def _string(self, table: dict[str, Any], key: str, key_path: str) -> str:
        if key not in table:
            self._missing_key(key_path, f"Add `{key}` with a non-empty string value.")
        value = table[key]
        if not isinstance(value, str):
            self._type_invalid(key_path, value, "a non-empty string")
        normalized = value.strip()
        if not normalized:
            self._rule_invalid(key_path, value, "a non-empty string")
        return normalized

    def _boolean(self, table: dict[str, Any], key: str, key_path: str) -> bool:
        if key not in table:
            self._missing_key(key_path, f"Add `{key} = true` or `{key} = false`.")
        value = table[key]
        if type(value) is not bool:
            self._type_invalid(key_path, value, "a TOML Boolean")
        return value

    def _integer(self, table: dict[str, Any], key: str, key_path: str) -> int:
        if key not in table:
            self._missing_key(key_path, f"Add `{key}` with an integer value.")
        value = table[key]
        if type(value) is not int:
            self._type_invalid(key_path, value, "a TOML integer")
        return value

    def _choice(
        self,
        table: dict[str, Any],
        key: str,
        key_path: str,
        choices: tuple[str, ...],
        code: str = "CONFIG-MODE-INVALID",
    ) -> str:
        value = self._string(table, key, key_path)
        if value not in choices:
            self._fail(
                code,
                key_path,
                value,
                list(choices),
                f"{key_path} has unsupported value {value!r}.",
                f"Set `{key} = \"{choices[0]}\"` or one of {', '.join(choices)}.",
            )
        return value

    def _strings(
        self,
        table: dict[str, Any],
        key: str,
        key_path: str,
        *,
        non_empty: bool,
    ) -> tuple[str, ...]:
        if key not in table:
            self._missing_key(key_path, f"Add `{key} = []` or an explicit string list.")
        value = table[key]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            self._type_invalid(key_path, value, "a list of strings")
        if non_empty and not value:
            self._rule_invalid(key_path, value, "a non-empty list of strings")
        result: list[str] = []
        for item in value:
            normalized = item.strip()
            if not normalized:
                self._rule_invalid(key_path, item, "non-empty string entries")
            if normalized in result:
                self._rule_invalid(key_path, item, "unique entries")
            result.append(normalized)
        return tuple(result)

    def _choices(
        self,
        table: dict[str, Any],
        key: str,
        key_path: str,
        choices: tuple[str, ...],
    ) -> tuple[str, ...]:
        values = self._strings(table, key, key_path, non_empty=False)
        for value in values:
            if value not in choices:
                self._rule_invalid(key_path, value, f"values from {', '.join(choices)}")
        return values

    def _path(self, table: dict[str, Any], key: str, key_path: str) -> str:
        return self._normalize_path(self._string(table, key, key_path), key_path)

    def _paths(
        self,
        table: dict[str, Any],
        key: str,
        key_path: str,
        *,
        non_empty: bool,
    ) -> tuple[str, ...]:
        values = self._strings(table, key, key_path, non_empty=non_empty)
        result: list[str] = []
        for value in values:
            normalized = self._normalize_path(value, key_path)
            if normalized in result:
                self._rule_invalid(key_path, value, "unique normalized repository paths")
            result.append(normalized)
        return tuple(result)

    def _globs(
        self,
        table: dict[str, Any],
        key: str,
        key_path: str,
        *,
        non_empty: bool,
    ) -> tuple[str, ...]:
        values = self._strings(table, key, key_path, non_empty=non_empty)
        result: list[str] = []
        for value in values:
            normalized = self._normalize_path(value, key_path, allow_glob=True)
            self._validate_glob(normalized, key_path)
            if normalized in result:
                self._rule_invalid(key_path, value, "unique normalized repository globs")
            result.append(normalized)
        return tuple(result)

    def _regexes(
        self, table: dict[str, Any], key: str, key_path: str
    ) -> tuple[str, ...]:
        values = self._strings(table, key, key_path, non_empty=False)
        for value in values:
            try:
                re.compile(value)
            except re.error as exc:
                self._rule_invalid(key_path, value, f"valid Python regular expressions ({exc})")
        return values

    def _commands(
        self, table: dict[str, Any], key: str, key_path: str
    ) -> tuple[str, ...]:
        return self._strings(table, key, key_path, non_empty=False)

    def _normalize_path(
        self, value: str, key_path: str, *, allow_glob: bool = False
    ) -> str:
        normalized = value.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        normalized = re.sub(r"/{2,}", "/", normalized).rstrip("/")
        if (
            not normalized
            or normalized.startswith(("/", "~"))
            or re.match(r"^[A-Za-z]:", normalized)
            or ".." in normalized.split("/")
        ):
            self._rule_invalid(key_path, value, "a repository-relative path without `..`")
        if not allow_glob and any(char in normalized for char in "*?[]"):
            self._rule_invalid(key_path, value, "a repository-relative path without globs")
        return normalized

    def _validate_glob(self, value: str, key_path: str) -> None:
        depth = 0
        for char in value:
            if char == "[":
                if depth:
                    self._rule_invalid(key_path, value, "a glob with balanced bracket expressions")
                depth = 1
            elif char == "]":
                if not depth:
                    self._rule_invalid(key_path, value, "a glob with balanced bracket expressions")
                depth = 0
        if depth:
            self._rule_invalid(key_path, value, "a glob with balanced bracket expressions")

    def _missing_key(self, key_path: str, remediation: str) -> NoReturn:
        self._fail(
            "CONFIG-KEY-MISSING",
            key_path,
            None,
            "a required key",
            f"Required configuration key {key_path} is missing.",
            f"{remediation} Then run `aegis config validate`.",
        )

    def _type_invalid(
        self, key_path: str, received: object, expected: object
    ) -> NoReturn:
        self._fail(
            "CONFIG-TYPE-INVALID",
            key_path,
            received,
            expected,
            f"{key_path or 'workflow.toml'} has the wrong type or is not part of schema 2.",
            f"Replace {key_path or 'the document'} with {expected}, then run `aegis config validate`.",
        )

    def _rule_invalid(
        self, key_path: str, received: object, expected: object
    ) -> NoReturn:
        self._fail(
            "CONFIG-RULE-INVALID",
            key_path,
            received,
            expected,
            f"{key_path} contains an invalid rule or value.",
            f"Use {expected} in {key_path}, then run `aegis config validate`.",
        )

    def _inconsistent(
        self, key_path: str, received: object, expected: object
    ) -> NoReturn:
        self._fail(
            "CONFIG-INCONSISTENT",
            key_path,
            received,
            expected,
            f"{key_path} contradicts its selected mode or another option.",
            f"Configure {expected}, then run `aegis config validate`.",
        )

    def _fail(
        self,
        code: str,
        key_path: str,
        received: object,
        expected: object,
        message: str,
        remediation: str | None = None,
    ) -> NoReturn:
        raise ConfigurationError(
            code=code,
            config_path=self.path,
            key_path=key_path,
            received=received,
            expected=expected,
            message=message,
            remediation=remediation
            or f"Correct {key_path} in .agentic/workflow.toml, then run `aegis config validate`.",
        )


# PUBLIC API


def load_config(repo_root: Path) -> WorkflowConfig:
    """
    @brief      Load and strictly validate `.agentic/workflow.toml`.
    @param[in]  repo_root Repository root containing `.agentic`.
    @return     Complete immutable schema-version-2 configuration.
    @exception  ConfigurationError If the file is unavailable or invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    1.0.0
    """
    root = repo_root.resolve()
    path = root / CONFIG_RELATIVE_PATH
    if not path.is_file():
        raise ConfigurationError(
            code="CONFIG-MISSING",
            config_path=path,
            key_path="",
            received=None,
            expected="a readable regular .agentic/workflow.toml file",
            message="Required workflow configuration is missing or is not a readable file.",
            remediation=(
                "Create .agentic/workflow.toml from the complete schema-version-2 template, "
                "then run `aegis config validate`."
            ),
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(
            code="CONFIG-MISSING",
            config_path=path,
            key_path="",
            received=type(exc).__name__,
            expected="a readable UTF-8 regular file",
            message="Required workflow configuration cannot be read.",
            remediation=(
                "Restore read access and valid UTF-8 content for .agentic/workflow.toml, "
                "then run `aegis config validate`."
            ),
        ) from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(
            code="CONFIG-TOML-INVALID",
            config_path=path,
            key_path="",
            received=str(exc),
            expected="valid TOML",
            message=".agentic/workflow.toml is not valid TOML.",
            remediation=(
                "Repair the TOML syntax using the shipped schema-version-2 template, "
                "then run `aegis config validate`."
            ),
        ) from None
    return _Parser(root, path, data).parse()


def effective_config_dict(config: WorkflowConfig) -> dict[str, object]:
    """
    @brief      Serialize the complete normalized effective configuration.
    @param[in]  config Validated workflow configuration.
    @return     Deterministically ordered JSON-compatible mapping.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.2.0
    """

    def policy(mode: str, **rules: object) -> dict[str, object]:
        """
        @brief      Serialize one mode and count its active flat or staged rules.
        @param[in]  mode Explicit policy mode.
        @param[in]  rules JSON-compatible rule collections and scalar details.
        @return     Policy mapping with a recursively counted active rule total.
        @version    0.2.0
        """
        active_count = sum(
            len(value)
            if isinstance(value, list)
            else sum(len(items) for items in value.values() if isinstance(items, list))
            if isinstance(value, dict)
            else 0
            for value in rules.values()
        )
        return {"mode": mode, "active_rule_count": active_count, **rules}

    stages = {name: list(config.write_access.stages[name]) for name in ALL_STAGES if name in config.write_access.stages}
    return {
        "schema_version": config.schema_version,
        "source": {"roots": list(config.source_roots)},
        "tests": {"roots": list(config.test_roots)},
        "requirements": {"roots": list(config.requirement_roots)},
        "documentation": {
            "roots": list(config.documentation_roots),
            "component_template": config.component_documentation_template,
        },
        "components": {
            "manifest": config.component_manifest,
            "baseline_guard": policy(
                config.component_baseline_guard.mode,
                minimum_completion_level=config.component_baseline_guard.minimum_completion_level,
            ),
        },
        "knowledge": {"roots": list(config.knowledge_roots)},
        "reports": {"adoption_root": config.adoption_report_root},
        "traceability": {
            "language": config.traceability_language,
            "source_extensions": list(config.source_extensions),
            "test_file_patterns": list(config.test_file_patterns),
            "coverage": policy(
                config.coverage.mode,
                coverable_roots=list(config.coverage.coverable_roots),
                exclude=list(config.coverage.exclude),
            ),
        },
        "adoption": {
            "allow_component_bundles": config.adoption_allow_component_bundles,
            "max_bundle_components": config.adoption_max_bundle_components,
            "source_changes": policy(config.adoption_source_changes.mode),
        },
        "alignment": {
            "enabled": config.alignment_enabled,
            "pause_on_open_questions": config.alignment_pause_on_open_questions,
            "risk_threshold": config.alignment_risk_threshold,
            "allow_recommended_responses": config.alignment_allow_recommended_responses,
            "protected_scope": policy(
                config.alignment_protected_scope.mode,
                patterns=list(config.alignment_protected_scope.patterns),
            ),
        },
        "gates": policy(
            config.gates.mode,
            test=list(config.gates.test),
            lint=list(config.gates.lint),
        ),
        "guardrails": {
            "secrets": policy(config.secrets.mode, patterns=list(config.secrets.patterns)),
            "protected_paths": policy(
                config.protected_paths.mode,
                patterns=list(config.protected_paths.patterns),
                operations=list(config.protected_paths.operations),
            ),
            "working_tree": policy(
                config.working_tree.mode,
                blocked_patterns=list(config.working_tree.blocked_patterns),
            ),
            "write_access": policy(config.write_access.mode, stages=stages),
            "scope": policy(
                config.scope.mode, allowed_roots=list(config.scope.allowed_roots)
            ),
            "delivery": policy(
                config.delivery.mode,
                command_patterns=list(config.delivery.command_patterns),
            ),
        },
    }


def configuration_error_json(error: ConfigurationError) -> str:
    """
    @brief      Render one configuration error as deterministic JSON.
    @param[in]  error Typed configuration failure.
    @return     Pretty-printed JSON object with one trailing newline omitted.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-22
    @version    0.1.0
    """
    return json.dumps(error.to_dict(), indent=2, ensure_ascii=False)


# END OF FILE
