"""Dependency-free local tool functions for agent and MCP integrations."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from claimbench.manifest import (
    ManifestError,
    load_json,
    load_manifest,
    validate_manifest_data,
)
from claimbench.paths import EXAMPLE_MANIFESTS_ROOT
from claimbench.report import generate_reproducibility_report, report_to_dict, report_to_markdown
from claimbench.storage.cached_runs import load_cached_run_results
from claimbench.storage.local_store import LocalStore


def list_papers_tool(manifest_root: Path = EXAMPLE_MANIFESTS_ROOT) -> dict[str, Any]:
    """Return dashboard-ready summaries for all known papers."""

    store = LocalStore(manifest_root)
    return {
        "papers": [
            store.paper_summary(paper_id)
            for paper_id in store.paper_ids()
        ]
    }


def validate_manifest_tool(path: Path) -> dict[str, Any]:
    """Validate a manifest and return structured issues instead of raising."""

    try:
        data = load_json(path)
        issues = validate_manifest_data(data)
    except ManifestError as exc:
        return {
            "valid": False,
            "path": str(path),
            "issues": [{"path": "$", "message": str(exc)}],
        }

    return {
        "valid": not issues,
        "path": str(path),
        "issues": [asdict(issue) for issue in issues],
    }


def claim_evidence_tool(
    paper_id: str,
    *,
    claim_id: str | None = None,
    manifest_root: Path = EXAMPLE_MANIFESTS_ROOT,
) -> dict[str, Any]:
    """Return cached/manifest evidence for one claim."""

    store = LocalStore(manifest_root)
    evidence = store.claim_evidence(paper_id, claim_id)
    return {
        "paper_id": paper_id,
        "evidence": asdict(evidence),
    }


def cached_report_tool(
    *,
    paper_id: str | None = None,
    manifest_path: Path | None = None,
    manifest_root: Path = EXAMPLE_MANIFESTS_ROOT,
    output_format: str = "json",
) -> dict[str, Any]:
    """Return a cached-run report for a known paper or manifest path."""

    if (paper_id is None) == (manifest_path is None):
        raise ValueError("Provide exactly one of paper_id or manifest_path.")

    if manifest_path is not None:
        manifest = load_manifest(manifest_path)
    else:
        manifest = LocalStore(manifest_root).get_manifest(str(paper_id))

    report = generate_reproducibility_report(manifest, load_cached_run_results(manifest))
    if output_format == "json":
        return {
            "format": "json",
            "paper_id": manifest.paper_id,
            "report": report_to_dict(report),
        }
    if output_format == "markdown":
        return {
            "format": "markdown",
            "paper_id": manifest.paper_id,
            "report": report_to_markdown(report),
        }

    raise ValueError(f"Unsupported report format: {output_format}. Expected 'json' or 'markdown'.")
