"""Manifest loading and validation for ClaimBench."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from claimbench.paths import EXAMPLE_MANIFESTS_ROOT, SCHEMA_PATH


class ManifestError(Exception):
    """Raised when a manifest cannot be loaded or validated."""


@dataclass(frozen=True)
class ValidationIssue:
    """A schema validation issue with a readable location."""

    path: str
    message: str


@dataclass(frozen=True)
class ClaimManifest:
    """Validated claim manifest plus its source path."""

    path: Path
    data: dict[str, Any]

    @property
    def paper_id(self) -> str:
        return str(self.data["paper"]["paper_id"])

    @property
    def title(self) -> str:
        return str(self.data["paper"]["title"])

    @property
    def claims(self) -> list[dict[str, Any]]:
        return list(self.data.get("claims", []))


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"Could not read {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError(f"Expected JSON object in {path}")
    return data


def load_schema(schema_path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """Load the ClaimManifest JSON schema."""

    return load_json(schema_path)


def validate_manifest_data(
    data: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> list[ValidationIssue]:
    """Validate manifest data and return schema issues."""

    validator = Draft202012Validator(schema or load_schema())
    issues: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        path = "$"
        if error.path:
            path += "." + ".".join(str(part) for part in error.path)
        issues.append(ValidationIssue(path=path, message=error.message))
    return issues


def load_manifest(path: Path, *, validate: bool = True) -> ClaimManifest:
    """Load a manifest file and optionally validate it."""

    data = load_json(path)
    if validate:
        issues = validate_manifest_data(data)
        if issues:
            formatted = "\n".join(f"- {issue.path}: {issue.message}" for issue in issues)
            raise ManifestError(f"Manifest validation failed for {path}:\n{formatted}")
    return ClaimManifest(path=path, data=data)


def discover_manifests(root: Path = EXAMPLE_MANIFESTS_ROOT) -> list[Path]:
    """Return all example manifest paths in deterministic order."""

    if not root.exists():
        return []
    return sorted(root.glob("*.manifest.json"))


def load_all_manifests(root: Path = EXAMPLE_MANIFESTS_ROOT) -> list[ClaimManifest]:
    """Load all manifests from a directory."""

    return [load_manifest(path) for path in discover_manifests(root)]
