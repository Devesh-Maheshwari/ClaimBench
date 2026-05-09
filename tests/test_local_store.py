from __future__ import annotations

from claimbench.storage.local_store import LocalStore


def test_local_store_exposes_all_gold_set_papers() -> None:
    store = LocalStore()

    assert store.paper_ids() == [
        "minirocket_2012_08791",
        "quant_2308_00928",
        "rocket_1910_13051",
    ]


def test_local_store_summary_and_claim_rows() -> None:
    store = LocalStore()

    summary = store.paper_summary("rocket_1910_13051")
    rows = store.claim_rows("rocket_1910_13051")

    assert summary["paper_id"] == "rocket_1910_13051"
    assert summary["num_claims"] == 2
    assert summary["overall_status"] == "needs_review"
    assert len(rows) == 2
    assert rows[0][0] == "rocket_claim_full_ucr_runtime"


def test_local_store_evidence_and_report_preview() -> None:
    store = LocalStore()

    evidence = store.claim_evidence("quant_2308_00928")
    report = store.report_preview("quant_2308_00928")

    assert evidence.claim_id == "quant_claim_full_ucr_runtime"
    assert evidence.command.startswith("python scripts/run_quant_single_dataset.py")
    assert "ClaimBench Report:" in report
    assert "quant_claim_full_ucr_runtime" in report
