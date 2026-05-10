from __future__ import annotations

from claimbench.dashboard.app import (
    claim_choices,
    evidence_markdown,
    environment_markdown,
    load_dashboard_manifests,
    overview_markdown,
    review_status_markdown,
)
from claimbench.storage.local_store import LocalStore


def test_dashboard_loads_gold_set_manifests() -> None:
    manifests = load_dashboard_manifests()

    assert len(manifests) == 3


def test_evidence_markdown_contains_claim_contract() -> None:
    store = LocalStore()
    evidence = store.claim_evidence("minirocket_2012_08791")

    rendered = evidence_markdown(evidence)

    assert "Evidence for `minirocket_claim_full_ucr_runtime`" in rendered
    assert "Expected metric" in rendered
    assert "Observed metric" in rendered
    assert "Command" in rendered


def test_overview_markdown_contains_demo_summary() -> None:
    store = LocalStore()
    summary = store.paper_summary("quant_2308_00928")

    rendered = overview_markdown(summary)

    assert "## QUANT" in rendered
    assert "Overall status" in rendered
    assert "Cached demo runs: `1`" in rendered
    assert "Local/self-hosted runs" in rendered
    assert "https://github.com/angus924/quant" in rendered


def test_environment_markdown_contains_resource_summary() -> None:
    store = LocalStore()
    environment = store.environment_summary("minirocket_2012_08791")

    rendered = environment_markdown(environment)

    assert "## Environment" in rendered
    assert "Execution mode: `docker`" in rendered
    assert "Base image: `python:3.10-slim`" in rendered
    assert "Dependency files: `requirements.txt`" in rendered


def test_review_status_markdown_contains_validation_context() -> None:
    store = LocalStore()
    review = store.review_status("rocket_1910_13051")

    rendered = review_status_markdown(review)

    assert "## Review Status" in rendered
    assert "Status: `draft`" in rendered
    assert "### Unresolved Fields" in rendered
    assert "Docker image digest" in rendered
    assert "Week 2 schema/dashboard work" in rendered


def test_claim_choices_returns_manifest_claim_ids() -> None:
    manifests = load_dashboard_manifests()
    minirocket = next(
        manifest for manifest in manifests if manifest.paper_id == "minirocket_2012_08791"
    )

    assert claim_choices(minirocket) == [
        "minirocket_claim_full_ucr_runtime",
        "minirocket_claim_repeatability",
    ]


def test_selected_claim_evidence_renders_specific_claim() -> None:
    store = LocalStore()
    evidence = store.claim_evidence(
        "minirocket_2012_08791",
        "minirocket_claim_repeatability",
    )

    rendered = evidence_markdown(evidence)

    assert "Evidence for `minirocket_claim_repeatability`" in rendered
    assert "repeatability" in rendered or "Repeatability" in rendered
    assert "Observed metric: `0.0`" in rendered
