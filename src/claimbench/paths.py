"""Path helpers for repository-local ClaimBench assets."""

from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PACKAGE_ROOT.parent
REPO_ROOT = SRC_ROOT.parent

SCHEMA_PATH = PACKAGE_ROOT / "schemas" / "claim_manifest.schema.json"
EXAMPLES_ROOT = REPO_ROOT / "examples"
EXAMPLE_MANIFESTS_ROOT = EXAMPLES_ROOT / "manifests"
FIXTURES_ROOT = EXAMPLES_ROOT / "fixtures"
SMOKE_MANIFEST_PATH = FIXTURES_ROOT / "manifests" / "smoke_test.manifest.json"
SMOKE_WORKSPACE_ROOT = FIXTURES_ROOT / "smoke_workspace"
REPORTS_ROOT = EXAMPLES_ROOT / "reports"
