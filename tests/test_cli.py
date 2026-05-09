from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claimbench.cli import app
from claimbench.manifest import ClaimManifest
from claimbench.runner.executor import ExperimentRunResult

runner = CliRunner()


def _write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "paper": {
                    "paper_id": "fixture",
                    "title": "Fixture Paper",
                    "arxiv_id": "0000.00000",
                    "repo_url": "https://example.com/repo.git",
                    "repo_commit": "abc123",
                    "domain": "fixture",
                },
                "claims": [
                    {
                        "claim_id": "claim_accuracy",
                        "text": "Fixture accuracy claim.",
                        "claim_type": "numeric_metric",
                        "paper_location": "Table 1",
                        "expected_metric": {
                            "name": "accuracy",
                            "value": 0.9,
                        },
                        "tolerance": {
                            "type": "absolute",
                            "value": 0.02,
                        },
                        "status": "executable",
                    }
                ],
                "experiments": [
                    {
                        "experiment_id": "exp_accuracy",
                        "command": ["python", "run.py"],
                        "working_directory": ".",
                        "metric_parser": {
                            "type": "json_path",
                            "target": "$.accuracy",
                        },
                        "linked_claim_ids": ["claim_accuracy"],
                    }
                ],
                "environment": {
                    "execution_mode": "docker",
                    "base_image": "python:3.11-slim",
                    "python_version": "3.11",
                },
                "datasets": [
                    {
                        "dataset_id": "fixture_dataset",
                        "name": "Fixture Dataset",
                        "source": "synthetic",
                    }
                ],
                "provenance": {
                    "created_by": "test",
                    "created_at": "2026-05-09T00:00:00Z",
                    "review_status": "draft",
                },
            }
        ),
        encoding="utf-8",
    )


def test_run_experiment_cli_routes_to_docker_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)
    calls: list[dict[str, object]] = []

    def fake_run_manifest_experiment_in_docker(
        manifest: ClaimManifest,
        experiment_id: str,
        **kwargs: object,
    ) -> ExperimentRunResult:
        calls.append(
            {
                "manifest": manifest,
                "experiment_id": experiment_id,
                **kwargs,
            }
        )
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="succeeded",
            command=["docker", "run"],
            returncode=0,
            runtime_seconds=0.1,
            stdout="done\n",
            stderr="",
            observed_metric=0.91,
            verdicts=[],
        )

    monkeypatch.setattr(
        "claimbench.cli.run_manifest_experiment_in_docker",
        fake_run_manifest_experiment_in_docker,
    )

    result = runner.invoke(
        app,
        [
            "run-experiment",
            str(manifest_path),
            "exp_accuracy",
            "--workspace",
            str(tmp_path),
            "--metric-output",
            "runs/metrics.json",
            "--timeout-seconds",
            "12",
            "--sandbox",
            "docker",
            "--docker-network",
            "none",
            "--docker-memory",
            "2g",
            "--docker-cpus",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert calls
    assert calls[0]["experiment_id"] == "exp_accuracy"
    assert calls[0]["workspace"] == tmp_path
    assert calls[0]["metric_output_path"] == Path("runs/metrics.json")
    assert calls[0]["timeout_seconds"] == 12
    assert calls[0]["image"] == "python:3.11-slim"
    assert calls[0]["network"] == "none"
    assert calls[0]["memory"] == "2g"
    assert calls[0]["cpus"] == "1"
    assert '"status": "succeeded"' in result.output


def test_run_experiment_cli_rejects_unknown_sandbox(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    result = runner.invoke(
        app,
        [
            "run-experiment",
            str(manifest_path),
            "exp_accuracy",
            "--sandbox",
            "podman",
        ],
    )

    assert result.exit_code == 1
    assert "Unsupported sandbox" in result.output
