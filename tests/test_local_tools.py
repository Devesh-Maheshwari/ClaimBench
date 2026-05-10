from __future__ import annotations

import json
from pathlib import Path

import pytest

from claimbench.paths import EXAMPLE_MANIFESTS_ROOT
from claimbench.tools.local import (
    cached_report_tool,
    claim_evidence_tool,
    list_papers_tool,
    validate_manifest_tool,
)


def test_list_papers_tool_returns_cached_run_summaries() -> None:
    payload = list_papers_tool()

    paper_ids = [paper["paper_id"] for paper in payload["papers"]]
    assert paper_ids == [
        "minirocket_2012_08791",
        "quant_2308_00928",
        "rocket_1910_13051",
    ]
    assert payload["papers"][0]["num_cached_runs"] > 0
    assert payload["papers"][0]["failure_category_counts"] == {"none": 2}


def test_validate_manifest_tool_reports_schema_issues(tmp_path: Path) -> None:
    manifest_path = tmp_path / "invalid.manifest.json"
    manifest_path.write_text(json.dumps({"schema_version": "0.1.0"}), encoding="utf-8")

    payload = validate_manifest_tool(manifest_path)

    assert payload["valid"] is False
    assert payload["issues"]
    assert any("required property" in issue["message"] for issue in payload["issues"])


def test_claim_evidence_tool_returns_observed_metric() -> None:
    payload = claim_evidence_tool(
        "minirocket_2012_08791",
        claim_id="minirocket_claim_repeatability",
    )

    assert payload["paper_id"] == "minirocket_2012_08791"
    assert payload["evidence"]["claim_id"] == "minirocket_claim_repeatability"
    assert payload["evidence"]["observed_metric"] == "0.0"
    assert payload["evidence"]["verdict"] == "needs_review"


def test_cached_report_tool_returns_json_report() -> None:
    payload = cached_report_tool(paper_id="quant_2308_00928")

    assert payload["format"] == "json"
    assert payload["paper_id"] == "quant_2308_00928"
    assert payload["report"]["summary"]["num_runs"] == 1
    assert payload["report"]["summary"]["failure_category_counts"] == {"none": 1}
    assert payload["report"]["experiments"][0]["status"] == "succeeded"
    assert payload["report"]["experiments"][0]["failure_category"] == "none"


def test_cached_report_tool_returns_markdown_for_manifest_path() -> None:
    payload = cached_report_tool(
        manifest_path=EXAMPLE_MANIFESTS_ROOT / "rocket_1910_13051.manifest.json",
        output_format="markdown",
    )

    assert payload["format"] == "markdown"
    assert "ClaimBench Report: ROCKET" in payload["report"]
    assert "Experiment runs: `2`" in payload["report"]
    assert "Failure category counts: `none=2`" in payload["report"]


def test_cached_report_tool_requires_one_report_target() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        cached_report_tool()

    with pytest.raises(ValueError, match="exactly one"):
        cached_report_tool(
            paper_id="rocket_1910_13051",
            manifest_path=EXAMPLE_MANIFESTS_ROOT / "rocket_1910_13051.manifest.json",
        )
