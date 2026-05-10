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


def test_local_store_paper_catalog_rows_summarize_all_papers() -> None:
    store = LocalStore()

    rows = store.paper_catalog_rows()

    assert [row[0] for row in rows] == [
        "minirocket_2012_08791",
        "quant_2308_00928",
        "rocket_1910_13051",
    ]
    assert rows[0][2] == "needs_review"
    assert rows[0][3] == 2
    assert rows[0][4] == 2
    assert rows[1][4] == 1
    assert "github.com" in rows[2][7]


def test_local_store_experiment_rows_include_cached_run_results() -> None:
    store = LocalStore()

    rows = store.experiment_rows("minirocket_2012_08791")

    assert rows[0][0] == "minirocket_exp_ucr_reduced"
    assert rows[0][2] == "succeeded"
    assert rows[0][3] == 12.8
    assert rows[0][5] == "minirocket_claim_full_ucr_runtime"
    assert "scripts/run_minirocket_single_dataset.py" in rows[0][6]


def test_local_store_cached_run_rows_include_artifact_metadata() -> None:
    store = LocalStore()

    rows = store.cached_run_rows("rocket_1910_13051")

    assert rows[0][0] == "rocket_cached_ucr_reduced_2026_05_09"
    assert rows[0][1] == "rocket_exp_ucr_reduced"
    assert rows[0][2] == "succeeded"
    assert '"runtime_seconds": 438.2' in rows[0][3]
    assert rows[0][4] == "cached://rocket/ucr_reduced/log.txt"
    assert rows[0][5] == "cached://rocket/ucr_reduced/metrics.csv"
    assert rows[0][6] == "2026-05-09T00:00:00Z"
    assert rows[0][7] == "2026-05-09T00:07:18Z"


def test_local_store_resource_rows_include_environment_and_datasets() -> None:
    store = LocalStore()

    environment = store.environment_summary("rocket_1910_13051")
    datasets = store.dataset_rows("rocket_1910_13051")

    assert environment["execution_mode"] == "docker"
    assert environment["base_image"] == "python:3.10-slim"
    assert environment["dependency_files"] == ["requirements.txt"]
    assert datasets[0][0] == "ucr_archive"
    assert datasets[0][4] == "not pinned"
    assert "selected small datasets" in datasets[0][5]


def test_local_store_review_status_includes_unresolved_fields() -> None:
    store = LocalStore()

    review = store.review_status("minirocket_2012_08791")

    assert review["review_status"] == "draft"
    assert review["created_by"] == "ClaimBench Week 2 manual review"
    assert review["extraction_model"] == "manual"
    assert "expected repeatability threshold" in review["unresolved_fields"]
    assert "Initial manifest drafted" in review["manual_edits"][0]


def test_local_store_local_commands_point_to_manifest() -> None:
    store = LocalStore()

    commands = store.local_commands("quant_2308_00928")

    assert commands["validate"] == (
        "claimbench validate-manifest examples/manifests/quant_2308_00928.manifest.json"
    )
    assert commands["markdown_report"].endswith("--format markdown")
    assert commands["json_report"].endswith("--format json")
    assert "agent-tool claim-evidence" in commands["cached_evidence"]
    assert "--paper-id quant_2308_00928" in commands["cached_evidence"]


def test_local_store_evidence_and_report_preview() -> None:
    store = LocalStore()

    evidence = store.claim_evidence("quant_2308_00928")
    report = store.report_preview("quant_2308_00928")

    assert evidence.claim_id == "quant_claim_full_ucr_runtime"
    assert evidence.command.startswith("python scripts/run_quant_single_dataset.py")
    assert "ClaimBench Report:" in report
    assert "quant_claim_full_ucr_runtime" in report
