from __future__ import annotations

from pathlib import Path

from claimbench.manifest import (
    EXAMPLE_MANIFESTS_ROOT,
    discover_manifests,
    load_all_manifests,
    load_manifest,
    validate_manifest_data,
)


def test_discovers_gold_set_manifests() -> None:
    paths = discover_manifests(EXAMPLE_MANIFESTS_ROOT)

    assert len(paths) == 3
    assert {path.name for path in paths} == {
        "minirocket_2012_08791.manifest.json",
        "quant_2308_00928.manifest.json",
        "rocket_1910_13051.manifest.json",
    }


def test_loads_all_gold_set_manifests() -> None:
    manifests = load_all_manifests(EXAMPLE_MANIFESTS_ROOT)

    assert {manifest.paper_id for manifest in manifests} == {
        "minirocket_2012_08791",
        "quant_2308_00928",
        "rocket_1910_13051",
    }
    assert all(manifest.claims for manifest in manifests)


def test_validation_reports_schema_issue(tmp_path: Path) -> None:
    manifest = load_manifest(EXAMPLE_MANIFESTS_ROOT / "rocket_1910_13051.manifest.json")
    invalid = dict(manifest.data)
    invalid.pop("paper")

    issues = validate_manifest_data(invalid)

    assert issues
    assert any("'paper' is a required property" in issue.message for issue in issues)
