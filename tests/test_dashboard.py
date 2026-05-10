from __future__ import annotations

from claimbench.dashboard.app import (
    claim_choices,
    evidence_markdown,
    load_dashboard_manifests,
    overview_markdown,
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
