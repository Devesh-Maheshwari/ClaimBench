from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from claimbench.manifest import ClaimManifest
from claimbench.runner.docker_runner import (
    build_docker_command,
    run_manifest_experiment_in_docker,
)


def _manifest(tmp_path: Path, *, working_directory: str = ".") -> ClaimManifest:
    return ClaimManifest(
        path=tmp_path / "manifest.json",
        data={
            "paper": {
                "paper_id": "fixture",
                "title": "Fixture",
            },
            "claims": [
                {
                    "claim_id": "claim_accuracy",
                    "expected_metric": {"value": 0.9},
                    "tolerance": {"type": "absolute", "value": 0.02},
                }
            ],
            "experiments": [
                {
                    "experiment_id": "exp_accuracy",
                    "command": ["python", "scripts/run.py"],
                    "working_directory": working_directory,
                    "metric_parser": {"type": "json_path", "target": "$.accuracy"},
                    "linked_claim_ids": ["claim_accuracy"],
                }
            ],
        },
    )


def test_build_docker_command_applies_sandbox_options(tmp_path: Path) -> None:
    command = build_docker_command(
        ["python", "scripts/run.py"],
        workspace=tmp_path,
        image="python:3.10-slim",
        container_workdir="/workspace/repo",
        network="none",
        memory="4g",
        cpus="2",
    )

    assert command == [
        "docker",
        "run",
        "--rm",
        "--volume",
        f"{tmp_path}:/workspace",
        "--workdir",
        "/workspace/repo",
        "--env",
        "PYTHONPATH=/workspace/src",
        "--network",
        "none",
        "--memory",
        "4g",
        "--cpus",
        "2",
        "python:3.10-slim",
        "python",
        "scripts/run.py",
    ]


def test_run_manifest_experiment_in_docker_parses_mounted_metric_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "runs" / "metrics.json"

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["docker", "run", "--rm"]
        assert command[-3:] == ["python:3.10-slim", "python", "scripts/run.py"]
        assert kwargs["timeout"] == 300
        metrics_path.parent.mkdir(parents=True)
        metrics_path.write_text(json.dumps({"accuracy": 0.91}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="done\n", stderr="")

    monkeypatch.setattr("claimbench.runner.docker_runner.subprocess.run", fake_run)

    result = run_manifest_experiment_in_docker(
        _manifest(tmp_path),
        "exp_accuracy",
        workspace=tmp_path,
        metric_output_path=Path("runs/metrics.json"),
    )

    assert result.status == "succeeded"
    assert result.returncode == 0
    assert result.observed_metric == 0.91
    assert result.verdicts[0].status == "reproduced"


def test_run_manifest_experiment_in_docker_reports_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial\n")

    monkeypatch.setattr("claimbench.runner.docker_runner.subprocess.run", fake_run)

    result = run_manifest_experiment_in_docker(
        _manifest(tmp_path),
        "exp_accuracy",
        workspace=tmp_path,
        timeout_seconds=1,
    )

    assert result.status == "timed_out"
    assert result.returncode is None
    assert result.stdout == "partial\n"
    assert result.error == "Docker run timed out after 1 seconds."


def test_run_manifest_experiment_in_docker_rejects_workdir_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must stay inside workspace"):
        run_manifest_experiment_in_docker(
            _manifest(tmp_path, working_directory="../outside"),
            "exp_accuracy",
            workspace=tmp_path,
        )
