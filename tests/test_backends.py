from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from claimbench.manifest import load_manifest
from claimbench.runner.backends import ExecutionContext, LocalDockerExecutor, RemoteGpuExecutor


def _minimal_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "paper": {
                    "paper_id": "t",
                    "title": "T",
                    "arxiv_id": "1",
                    "repo_url": "https://example.com",
                    "repo_commit": "c",
                    "domain": "d",
                },
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "claim",
                        "claim_type": "numeric_metric",
                        "paper_location": "p",
                        "expected_metric": {"name": "m", "value": "to_be_measured"},
                        "tolerance": {"type": "manual", "value": "x", "rationale": "r"},
                        "linked_experiment_ids": ["e1"],
                        "status": "needs_review",
                    }
                ],
                "experiments": [
                    {
                        "experiment_id": "e1",
                        "command": ["python", "-c", "print(99)"],
                        "working_directory": ".",
                        "metric_parser": {"type": "regex", "target": r"(\d+)"},
                        "linked_claim_ids": ["c1"],
                    }
                ],
                "environment": {
                    "execution_mode": "docker",
                    "base_image": "python:3.10-slim",
                    "python_version": "3.10",
                },
                "datasets": [
                    {"dataset_id": "d1", "name": "D", "source": "synthetic"}
                ],
                "provenance": {"created_by": "test", "created_at": "2026-01-01", "review_status": "draft"},
            }
        ),
        encoding="utf-8",
    )


def test_remote_gpu_executor_returns_handle(tmp_path: Path) -> None:
    manifest_path = tmp_path / "m.json"
    _minimal_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    ex = RemoteGpuExecutor()
    ctx = ExecutionContext(workspace=tmp_path, timeout_seconds=30)
    h = ex.run_experiment(manifest, "e1", metric_output_path=None, ctx=ctx)
    assert h.status == "queued"
    assert h.run_id.startswith("gpu-stub-")


def test_local_docker_executor_local_runs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "m.json"
    _minimal_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    ex = LocalDockerExecutor(sandbox="local")
    ctx = ExecutionContext(workspace=tmp_path, timeout_seconds=30)
    r = ex.run_experiment(manifest, "e1", metric_output_path=None, ctx=ctx)
    assert r.status == "needs_review"
    assert r.observed_metric == "99"


@patch("claimbench.runner.backends.run_manifest_experiment_in_docker")
def test_local_docker_executor_docker_delegates(mock_docker, tmp_path: Path) -> None:
    manifest_path = tmp_path / "m.json"
    _minimal_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    from claimbench.runner.executor import ExperimentRunResult

    mock_docker.return_value = ExperimentRunResult(
        experiment_id="e1",
        status="succeeded",
        command=[],
        returncode=0,
        runtime_seconds=1.0,
        stdout="",
        stderr="",
        observed_metric=1.0,
        verdicts=[],
    )
    ex = LocalDockerExecutor(sandbox="docker")
    ctx = ExecutionContext(workspace=tmp_path, timeout_seconds=30)
    r = ex.run_experiment(manifest, "e1", metric_output_path=None, ctx=ctx)
    assert r.observed_metric == 1.0
    mock_docker.assert_called_once()
