#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file components.py
@brief Component manifest loading and audit helpers.
@details Provides the approved component and bundle contract for adoption runs,
using the shared repository path-matching policy for component ownership.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import tomllib

from .config import WorkflowConfig
from .errors import CommandInputError
from .paths import matches_pattern


# CONSTANTS

BASELINE_ORDER = {
    "unknown": 0,
    "discovered": 1,
    "characterized": 2,
    "baseline-usable": 3,
    "baseline-strict": 4,
}


# DATA MODELS / TYPEDEFINITIONS

@dataclass
class Component:
    """
    @brief      Represent an approved component boundary.
    """
    name: str
    paths: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    criticality: str = "medium"
    adoption_status: str = "unknown"
    owner: str = ""
    notes: str = ""


@dataclass
class ComponentBundle:
    """
    @brief      Represent an approved component bundle.
    """
    name: str
    components: list[str] = field(default_factory=list)
    reason: str = ""
    adoption_status: str = "unknown"
    approved: bool = False


@dataclass
class ComponentManifest:
    """
    @brief      Represent the loaded component manifest contract.
    """
    components: dict[str, Component] = field(default_factory=dict)
    bundles: dict[str, ComponentBundle] = field(default_factory=dict)


@dataclass
class ComponentIssue:
    """
    @brief      Represent a component manifest audit issue.
    """
    code: str
    message: str
    path: str | None = None
    name: str | None = None
    severity: str = "error"
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        """
        @brief      Convert a component issue to a serializable dictionary.
        @return     Dictionary representation of the issue.
        @exception  None
        """
        return asdict(self)


# PUBLIC API

def load_components(repo_root: Path, manifest_path: str) -> ComponentManifest:
    """
    @brief      Load the component manifest for a repository.
    @param[in]  repo_root Repository root.
    @param[in]  manifest_path Repository-relative manifest path.
    @return     Loaded component manifest, or an empty manifest when missing.
    @exception  CommandInputError If the manifest TOML is invalid.
    """
    path = repo_root / manifest_path
    if not path.exists():
        return ComponentManifest()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeError) as exc:
        raise CommandInputError(
            f"cannot load component manifest {manifest_path}: {exc}"
        ) from exc
    component_data = data.get("components", {})
    bundle_data = data.get("bundles", {})

    return ComponentManifest(
        components={
            name: _component_from_data(name, values)
            for name, values in component_data.items()
            if isinstance(values, dict)
        },
        bundles={
            name: _bundle_from_data(name, values)
            for name, values in bundle_data.items()
            if isinstance(values, dict)
        },
    )


def component_for_path(manifest: ComponentManifest, repo_relative_path: str) -> Component | None:
    """
    @brief      Find the component that owns a repository-relative path.
    @param[in]  manifest Loaded component manifest.
    @param[in]  repo_relative_path Repository-relative file path.
    @return     Matching component, or None when no component pattern matches.
    @exception  None
    """
    normalized = _normalize_path(repo_relative_path)
    for component in manifest.components.values():
        if any(matches_pattern(normalized, pattern) for pattern in component.paths):
            return component
    return None


def has_usable_baseline(status: str, minimum: str) -> bool:
    """
    @brief      Compare an adoption status against a required baseline.
    @param[in]  status Adoption status to test.
    @param[in]  minimum Minimum adoption status accepted as usable.
    @return     True when status meets or exceeds the requested minimum.
    @exception  ValueError If the required completion level is unsupported.
    """
    if minimum not in BASELINE_ORDER:
        raise ValueError(f"Unsupported baseline completion level: {minimum}")
    return BASELINE_ORDER.get(status, -1) >= BASELINE_ORDER[minimum]


def audit_components(
    repo_root: Path,
    config: WorkflowConfig,
    manifest_path: str | None = None,
) -> list[ComponentIssue]:
    """
    @brief      Audit the component manifest contract.
    @param[in]  repo_root Repository root.
    @param[in]  config Validated workflow configuration.
    @param[in]  manifest_path Optional repository-relative manifest path override.
    @return     List of component manifest audit issues.
    @exception  CommandInputError If the manifest TOML is invalid.
    """
    resolved_manifest_path = (
        config.component_manifest if manifest_path is None else manifest_path
    )
    manifest = load_components(repo_root, resolved_manifest_path)
    issues: list[ComponentIssue] = []

    for component in manifest.components.values():
        if component.adoption_status not in BASELINE_ORDER:
            issues.append(
                ComponentIssue(
                    code="COMPONENT-STATUS-INVALID",
                    message=f"{component.name} has invalid adoption_status {component.adoption_status}",
                    name=component.name,
                )
            )

    for bundle in manifest.bundles.values():
        if bundle.adoption_status not in BASELINE_ORDER:
            issues.append(
                ComponentIssue(
                    code="COMPONENT-BUNDLE-STATUS-INVALID",
                    message=f"{bundle.name} has invalid adoption_status {bundle.adoption_status}",
                    name=bundle.name,
                )
            )
        if not config.adoption_allow_component_bundles:
            issues.append(
                ComponentIssue(
                    code="COMPONENT-BUNDLE-DISALLOWED",
                    message=f"{bundle.name} is configured but component bundles are disabled",
                    name=bundle.name,
                )
            )
        if len(bundle.components) > config.adoption_max_bundle_components:
            issues.append(
                ComponentIssue(
                    code="COMPONENT-BUNDLE-TOO-LARGE",
                    message=(
                        f"{bundle.name} includes {len(bundle.components)} components; "
                        f"maximum is {config.adoption_max_bundle_components}"
                    ),
                    name=bundle.name,
                )
            )
        for component_name in bundle.components:
            if component_name not in manifest.components:
                issues.append(
                    ComponentIssue(
                        code="COMPONENT-BUNDLE-UNKNOWN-COMPONENT",
                        message=f"{bundle.name} references unknown component {component_name}",
                        name=bundle.name,
                    )
                )
    return issues


def audit_local_scope(
    repo_root: Path,
    paths: list[str],
    config: WorkflowConfig,
    minimum: str | None = None,
) -> list[ComponentIssue]:
    """
    @brief      Audit changed paths against component baseline requirements.
    @param[in]  repo_root Repository root.
    @param[in]  paths Repository-relative paths to inspect.
    @param[in]  config Validated workflow configuration.
    @param[in]  minimum Optional minimum adoption status override.
    @return     Blocking component scope issues.
    @exception  CommandInputError If the manifest TOML is invalid.
    """
    resolved_minimum = (
        minimum or config.component_baseline_guard.minimum_completion_level
    )
    if resolved_minimum is None:
        return []
    manifest = load_components(repo_root, config.component_manifest)
    issues: list[ComponentIssue] = []
    for path in paths:
        normalized = _normalize_path(path)
        component = component_for_path(manifest, normalized)
        if component is None:
            continue
        if has_usable_baseline(component.adoption_status, resolved_minimum):
            continue
        if _component_has_bundle_baseline(
            manifest, component.name, resolved_minimum
        ):
            continue
        issues.append(
            ComponentIssue(
                code="COMPONENT-BASELINE-MISSING",
                message=(
                    f"{component.name} is {component.adoption_status}; "
                    f"{resolved_minimum} is required before behavior-changing work"
                ),
                path=normalized,
                name=component.name,
            )
        )
    return issues


# LOCAL HELPERS

def _component_from_data(name: str, values: dict[str, Any]) -> Component:
    """
    @brief      Build a component model from manifest data.
    @param[in]  name Component name.
    @param[in]  values Component TOML table values.
    @return     Component model.
    @exception  None
    """
    return Component(
        name=name,
        paths=_normalize_list(values.get("paths", [])),
        tests=_normalize_list(values.get("tests", [])),
        criticality=str(values.get("criticality", "medium")),
        adoption_status=str(values.get("adoption_status", "unknown")),
        owner=str(values.get("owner", "")),
        notes=str(values.get("notes", "")),
    )


def _bundle_from_data(name: str, values: dict[str, Any]) -> ComponentBundle:
    """
    @brief      Build a component bundle model from manifest data.
    @param[in]  name Bundle name.
    @param[in]  values Bundle TOML table values.
    @return     Component bundle model.
    @exception  None
    """
    return ComponentBundle(
        name=name,
        components=_normalize_list(values.get("components", [])),
        reason=str(values.get("reason", "")),
        adoption_status=str(values.get("adoption_status", "unknown")),
        approved=bool(values.get("approved", False)),
    )


def _normalize_list(value: Any) -> list[str]:
    """
    @brief      Normalize a manifest list value.
    @param[in]  value Manifest value.
    @return     String list with normalized path separators.
    @exception  None
    """
    if not isinstance(value, list):
        return []
    return [_normalize_path(str(item)) for item in value]


def _component_has_bundle_baseline(manifest: ComponentManifest, component_name: str, minimum: str) -> bool:
    """
    @brief      Check whether an approved bundle satisfies a component baseline.
    @param[in]  manifest Loaded component manifest.
    @param[in]  component_name Component name to inspect.
    @param[in]  minimum Minimum adoption status accepted as usable.
    @return     True when an approved bundle satisfies the baseline contract.
    @exception  None
    """
    for bundle in manifest.bundles.values():
        if not bundle.approved or component_name not in bundle.components:
            continue
        if has_usable_baseline(bundle.adoption_status, minimum):
            return True
        if all(
            name in manifest.components
            and has_usable_baseline(manifest.components[name].adoption_status, minimum)
            for name in bundle.components
        ):
            return True
    return False


def _normalize_path(value: str) -> str:
    """
    @brief      Normalize repository-relative path text.
    @param[in]  value Path text.
    @return     Path using forward slashes.
    @exception  None
    """
    return value.replace("\\", "/").strip()


# END OF FILE
