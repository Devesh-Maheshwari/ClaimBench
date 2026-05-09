from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from claimbench.manifest import load_json, load_manifest
from claimbench.paths import EXAMPLE_MANIFESTS_ROOT
from claimbench.runner.executor import ExperimentRunResult
from claimbench.storage.cached_runs import (
    build_cached_run_record,
    import_cached_run_record,
    import_cached_run_record_data,
    load_cached_run_results,
)


def test_cached_runs_convert_to_runner_results() -> None:
    manifest = load_manifest(EXAMPLE_MANIFESTS_ROOT / "rocket_1910_13051.manifest.json")

    results = load_cached_run_results(manifest)

    assert [result.experiment_id for result in results] == [
        "rocket_exp_ucr_reduced",
        "rocket_exp_single_dataset",
    ]
    assert results[0].status == "succeeded"
    assert results[0].observed_metric == 438.2
    assert results[0].runtime_seconds == 438.2
    assert results[1].observed_metric == 1.0
    assert results[1].verdicts[0].status == "needs_review"


def test_cached_runs_are_loaded_for_all_gold_manifests() -> None:
    for path in sorted(EXAMPLE_MANIFESTS_ROOT.glob("*.manifest.json")):
        manifest = load_manifest(path)
        assert load_cached_run_results(manifest), path.name


def test_build_cached_run_record_from_runner_result() -> None:
    manifest = load_manifest(EXAMPLE_MANIFESTS_ROOT / "quant_2308_00928.manifest.json")
    result = ExperimentRunResult(
        experiment_id="quant_exp_single_dataset",
        status="succeeded",
        command=["python", "scripts/run_quant_single_dataset.py"],
        returncode=0,
        runtime_seconds=9.7,
        stdout="done\n",
        stderr="",
        observed_metric=1.0,
        verdicts=[],
    )

    record = build_cached_run_record(
        manifest,
        result,
        run_id="quant_test_run",
        artifact_uri="runs/quant/metrics.json",
        log_uri="runs/quant/log.txt",
        finished_at="2026-05-09T00:00:00+00:00",
    )

    assert record == {
        "run_id": "quant_test_run",
        "experiment_id": "quant_exp_single_dataset",
        "status": "succeeded",
        "metrics": {
            "accuracy": 1.0,
            "runtime_seconds": 9.7,
            "returncode": 0,
        },
        "log_uri": "runs/quant/log.txt",
        "artifact_uris": ["runs/quant/metrics.json"],
        "started_at": None,
        "finished_at": "2026-05-09T00:00:00+00:00",
    }


def test_build_cached_run_record_maps_needs_review_to_succeeded() -> None:
    manifest = load_manifest(EXAMPLE_MANIFESTS_ROOT / "rocket_1910_13051.manifest.json")
    result = ExperimentRunResult(
        experiment_id="rocket_exp_single_dataset",
        status="needs_review",
        command=["python", "scripts/run_rocket_single_dataset.py"],
        returncode=0,
        runtime_seconds=31.4,
        stdout="done\n",
        stderr="",
        observed_metric=1.0,
        verdicts=[],
    )

    record = build_cached_run_record(
        manifest,
        result,
        run_id="rocket_test_run",
        finished_at="2026-05-09T00:00:00+00:00",
    )

    assert record["status"] == "succeeded"
    assert record["metrics"]["accuracy"] == 1.0


def test_import_cached_run_record_appends_to_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "quant.manifest.json"
    record_path = tmp_path / "record.json"
    shutil.copyfile(EXAMPLE_MANIFESTS_ROOT / "quant_2308_00928.manifest.json", manifest_path)
    record = {
        "run_id": "quant_new_run",
        "experiment_id": "quant_exp_single_dataset",
        "status": "succeeded",
        "metrics": {
            "accuracy": 0.95,
            "runtime_seconds": 8.5,
        },
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")

    result = import_cached_run_record(manifest_path, record_path)
    updated = load_json(manifest_path)

    assert result["action"] == "added"
    assert result["num_cached_runs"] == 2
    assert updated["cached_runs"][-1]["run_id"] == "quant_new_run"


def test_import_cached_run_record_rejects_duplicate_without_replace(tmp_path: Path) -> None:
    manifest_path = tmp_path / "quant.manifest.json"
    shutil.copyfile(EXAMPLE_MANIFESTS_ROOT / "quant_2308_00928.manifest.json", manifest_path)
    record = {
        "run_id": "quant_cached_single_dataset_2026_05_09",
        "experiment_id": "quant_exp_single_dataset",
        "status": "succeeded",
        "metrics": {"accuracy": 0.95},
    }

    with pytest.raises(ValueError, match="already exists"):
        import_cached_run_record_data(manifest_path, record)


def test_import_cached_run_record_replaces_existing_record(tmp_path: Path) -> None:
    manifest_path = tmp_path / "quant.manifest.json"
    shutil.copyfile(EXAMPLE_MANIFESTS_ROOT / "quant_2308_00928.manifest.json", manifest_path)
    record = {
        "run_id": "quant_cached_single_dataset_2026_05_09",
        "experiment_id": "quant_exp_single_dataset",
        "status": "succeeded",
        "metrics": {
            "accuracy": 0.95,
            "runtime_seconds": 8.5,
        },
    }

    result = import_cached_run_record_data(manifest_path, record, replace=True)
    updated = load_json(manifest_path)

    assert result["action"] == "replaced"
    assert result["num_cached_runs"] == 1
    assert updated["cached_runs"][0]["metrics"]["accuracy"] == 0.95
