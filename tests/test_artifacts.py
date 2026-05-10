from __future__ import annotations

import json
from pathlib import Path

from claimbench.manifest import ClaimManifest
from claimbench.runner.artifacts import write_run_artifacts
from claimbench.runner.executor import ExperimentRunResult


def _manifest(tmp_path: Path) -> ClaimManifest:
    return ClaimManifest(
        path=tmp_path / "manifest.json",
        data={
            "paper": {
                "paper_id": "fixture",
                "title": "Fixture Paper",
            },
            "claims": [],
            "experiments": [
                {
                    "experiment_id": "exp_accuracy",
                    "command": ["python", "run.py"],
                    "metric_parser": {"type": "json_path", "target": "$.accuracy"},
                    "linked_claim_ids": [],
                }
            ],
        },
    )


def test_write_run_artifacts_writes_result_logs_and_cache_record(tmp_path: Path) -> None:
    result = ExperimentRunResult(
        experiment_id="exp_accuracy",
        status="succeeded",
        command=["python", "run.py"],
        returncode=0,
        runtime_seconds=1.2,
        stdout="hello\n",
        stderr="warning\n",
        observed_metric=0.91,
        verdicts=[],
    )

    summary = write_run_artifacts(
        _manifest(tmp_path),
        result,
        tmp_path / "artifacts",
        metric_output_path=Path("runs/metrics.json"),
    )

    result_payload = json.loads(Path(summary["result_path"]).read_text(encoding="utf-8"))
    cache_record = json.loads(Path(summary["cache_record_path"]).read_text(encoding="utf-8"))

    assert result_payload["experiment_id"] == "exp_accuracy"
    assert result_payload["observed_metric"] == 0.91
    assert Path(summary["stdout_path"]).read_text(encoding="utf-8") == "hello\n"
    assert Path(summary["stderr_path"]).read_text(encoding="utf-8") == "warning\n"
    assert cache_record["metrics"]["accuracy"] == 0.91
    assert cache_record["artifact_uris"] == ["runs/metrics.json"]
