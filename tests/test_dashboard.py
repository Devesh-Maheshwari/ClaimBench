from __future__ import annotations

from claimbench.dashboard.app import evidence_markdown, load_dashboard_manifests
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
