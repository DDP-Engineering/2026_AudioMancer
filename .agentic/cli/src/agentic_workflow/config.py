# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class WorkflowConfig:
    source_roots: list[str] = field(default_factory=lambda: ["src", "app", "lib"])
    test_roots: list[str] = field(default_factory=lambda: ["tests", "test"])
    spec_roots: list[str] = field(default_factory=lambda: [".agentic/specs", "spec"])
    requirement_roots: list[str] = field(default_factory=lambda: [".agentic/requirements"])
    documentation_roots: list[str] = field(default_factory=lambda: ["05_SoftwareDocu"])
    component_documentation_template: str = "05_SoftwareDocu/component_documentation_template.md"
    traceability_language: str = "python"
    source_extensions: list[str] = field(default_factory=lambda: [".py"])
    coverable_roots: list[str] = field(default_factory=lambda: ["src", "app", "lib"])
    coverable_exclude: list[str] = field(default_factory=lambda: ["__init__.py"])
    test_file_patterns: list[str] = field(default_factory=lambda: ["test_*.py", "*_test.py"])
    gate_commands: dict[str, list[str]] = field(default_factory=dict)
    secret_patterns: list[str] = field(default_factory=list)
    write_zones: dict[str, list[str]] = field(default_factory=dict)


def load_config(repo_root: Path) -> WorkflowConfig:
    path = repo_root / ".agentic" / "workflow.toml"
    if not path.exists():
        return WorkflowConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    gates = data.get("gates", {})
    traceability = data.get("traceability", {})
    documentation = data.get("documentation", {})
    return WorkflowConfig(
        source_roots=list(data.get("source", {}).get("roots", ["src", "app", "lib"])),
        test_roots=list(data.get("tests", {}).get("roots", ["tests", "test"])),
        spec_roots=list(data.get("spec", {}).get("roots", [".agentic/specs", "spec"])),
        requirement_roots=list(data.get("requirements", {}).get("roots", [".agentic/requirements"])),
        documentation_roots=list(documentation.get("roots", ["05_SoftwareDocu"])),
        component_documentation_template=str(
            documentation.get("component_template", "05_SoftwareDocu/component_documentation_template.md")
        ),
        traceability_language=str(traceability.get("language", "python")),
        source_extensions=list(traceability.get("source_extensions", [".py"])),
        coverable_roots=list(traceability.get("coverable_roots", data.get("source", {}).get("roots", ["src", "app", "lib"]))),
        coverable_exclude=list(traceability.get("coverable_exclude", ["__init__.py"])),
        test_file_patterns=list(traceability.get("test_file_patterns", ["test_*.py", "*_test.py"])),
        gate_commands={key: list(value) for key, value in gates.items()},
        secret_patterns=list(data.get("secrets", {}).get("patterns", [])),
        write_zones={
            key: list(value)
            for key, value in data.get("write_zones", {}).items()
        },
    )
