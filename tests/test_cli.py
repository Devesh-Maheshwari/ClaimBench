from __future__ import annotations

import sys
import json
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claimbench.cli import app
from claimbench.manifest import ClaimManifest
from claimbench.mcp_server import McpDependencyError
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
                        "linked_experiment_ids": ["exp_accuracy"],
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
                "cached_runs": [
                    {
                        "run_id": "fixture_cached_accuracy",
                        "experiment_id": "exp_accuracy",
                        "status": "succeeded",
                        "metrics": {
                            "accuracy": 0.91,
                            "runtime_seconds": 1.2,
                        },
                    }
                ],
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


def test_list_papers_cli_shows_status_and_failure_summary(tmp_path: Path) -> None:
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir()
    _write_manifest(manifest_root / "fixture.manifest.json")

    result = runner.invoke(
        app,
        ["list-papers", "--root", str(manifest_root)],
        terminal_width=200,
    )

    assert result.exit_code == 0
    assert "fixture" in result.output
    assert "reproduced" in result.output
    assert "none=1" in result.output


def test_run_experiment_cli_writes_cache_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    cache_record = tmp_path / "runs" / "cache_record.json"
    _write_manifest(manifest_path)

    def fake_run_manifest_experiment(
        manifest: ClaimManifest,
        experiment_id: str,
        **kwargs: object,
    ) -> ExperimentRunResult:
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="succeeded",
            command=["python", "run.py"],
            returncode=0,
            runtime_seconds=1.2,
            stdout="done\n",
            stderr="",
            observed_metric=0.91,
            verdicts=[],
        )

    monkeypatch.setattr(
        "claimbench.cli.run_manifest_experiment",
        fake_run_manifest_experiment,
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
            "--cache-record-output",
            str(cache_record),
        ],
    )

    assert result.exit_code == 0
    assert "Cached run record written" in result.output
    record = json.loads(cache_record.read_text(encoding="utf-8"))
    assert record["experiment_id"] == "exp_accuracy"
    assert record["metrics"]["accuracy"] == 0.91
    assert record["metrics"]["runtime_seconds"] == 1.2
    assert record["artifact_uris"] == ["runs/metrics.json"]


def test_run_experiment_cli_writes_artifact_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    artifact_dir = tmp_path / "artifacts"
    _write_manifest(manifest_path)

    def fake_run_manifest_experiment(
        manifest: ClaimManifest,
        experiment_id: str,
        **kwargs: object,
    ) -> ExperimentRunResult:
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="succeeded",
            command=["python", "run.py"],
            returncode=0,
            runtime_seconds=1.2,
            stdout="hello\n",
            stderr="warning\n",
            observed_metric=0.91,
            verdicts=[],
        )

    monkeypatch.setattr(
        "claimbench.cli.run_manifest_experiment",
        fake_run_manifest_experiment,
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
            "--artifact-dir",
            str(artifact_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Run artifacts written" in result.output
    assert (artifact_dir / "result.json").exists()
    assert (artifact_dir / "stdout.txt").read_text(encoding="utf-8") == "hello\n"
    assert (artifact_dir / "stderr.txt").read_text(encoding="utf-8") == "warning\n"
    cache_record = json.loads((artifact_dir / "cache_record.json").read_text(encoding="utf-8"))
    assert cache_record["metrics"]["accuracy"] == 0.91


def test_import_cache_record_cli_appends_record(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    record_path = tmp_path / "record.json"
    _write_manifest(manifest_path)
    record_path.write_text(
        json.dumps(
            {
                "run_id": "fixture_new_cached_accuracy",
                "experiment_id": "exp_accuracy",
                "status": "succeeded",
                "metrics": {
                    "accuracy": 0.92,
                    "runtime_seconds": 1.1,
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "import-cache-record",
            str(manifest_path),
            str(record_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "added"
    assert payload["num_cached_runs"] == 2
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated["cached_runs"][-1]["run_id"] == "fixture_new_cached_accuracy"


def test_smoke_test_cli_writes_artifacts(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "smoke_artifacts"

    result = runner.invoke(app, ["smoke-test", "--artifact-dir", str(artifact_dir)])

    assert result.exit_code == 0
    assert "Smoke test status" in result.output
    assert '"status": "succeeded"' in result.output
    assert (artifact_dir / "result.json").exists()
    assert (artifact_dir / "cache_record.json").exists()
    cache_record = json.loads((artifact_dir / "cache_record.json").read_text(encoding="utf-8"))
    assert cache_record["experiment_id"] == "smoke_exp_accuracy"
    assert cache_record["metrics"]["accuracy"] == 0.91


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


def test_report_cli_renders_markdown_with_cached_runs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    result = runner.invoke(app, ["report", str(manifest_path)])

    assert result.exit_code == 0
    assert "ClaimBench Report: Fixture Paper" in result.output
    assert "Experiment runs: `1`" in result.output
    assert "Observed: `0.91`" in result.output
    assert "Observed metric is within tolerance." in result.output


def test_report_cli_renders_json_without_cached_runs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    result = runner.invoke(
        app,
        [
            "report",
            str(manifest_path),
            "--format",
            "json",
            "--no-cached-runs",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["summary"]["num_runs"] == 0
    assert data["claims"][0]["observed_metric"] is None


def test_report_cli_writes_markdown_output_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "reports" / "fixture.md"
    _write_manifest(manifest_path)

    result = runner.invoke(
        app,
        [
            "report",
            str(manifest_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert "Report written" in result.output
    rendered = output_path.read_text(encoding="utf-8")
    assert "ClaimBench Report: Fixture Paper" in rendered
    assert "Observed: `0.91`" in rendered


def test_report_cli_writes_json_output_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "reports" / "fixture.json"
    _write_manifest(manifest_path)

    result = runner.invoke(
        app,
        [
            "report",
            str(manifest_path),
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["paper"]["paper_id"] == "fixture"
    assert payload["summary"]["num_runs"] == 1


def test_export_reports_cli_writes_all_manifest_reports(tmp_path: Path) -> None:
    manifest_root = tmp_path / "manifests"
    output_dir = tmp_path / "reports"
    manifest_root.mkdir()
    _write_manifest(manifest_root / "fixture.manifest.json")

    result = runner.invoke(
        app,
        [
            "export-reports",
            "--root",
            str(manifest_root),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Reports written" in result.output
    rendered = (output_dir / "fixture.md").read_text(encoding="utf-8")
    assert "ClaimBench Report: Fixture Paper" in rendered
    assert "Observed: `0.91`" in rendered


def test_export_reports_cli_writes_json_reports_without_cached_runs(tmp_path: Path) -> None:
    manifest_root = tmp_path / "manifests"
    output_dir = tmp_path / "reports"
    manifest_root.mkdir()
    _write_manifest(manifest_root / "fixture.manifest.json")

    result = runner.invoke(
        app,
        [
            "export-reports",
            "--root",
            str(manifest_root),
            "--output-dir",
            str(output_dir),
            "--format",
            "json",
            "--no-cached-runs",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((output_dir / "fixture.json").read_text(encoding="utf-8"))
    assert payload["summary"]["num_runs"] == 0


def test_export_reports_cli_handles_empty_manifest_root(tmp_path: Path) -> None:
    manifest_root = tmp_path / "empty"
    manifest_root.mkdir()

    result = runner.invoke(app, ["export-reports", "--root", str(manifest_root)])

    assert result.exit_code == 0
    assert "No manifests found" in result.output


def test_report_cli_rejects_unknown_format(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    result = runner.invoke(app, ["report", str(manifest_path), "--format", "html"])

    assert result.exit_code == 1
    assert "Unsupported report format" in result.output


def test_agent_tool_cli_lists_papers() -> None:
    result = runner.invoke(app, ["agent-tool", "list-papers"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["papers"][0]["paper_id"] == "minirocket_2012_08791"
    assert data["papers"][0]["num_cached_runs"] > 0


def test_agent_tool_cli_returns_claim_evidence() -> None:
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "claim-evidence",
            "--paper-id",
            "quant_2308_00928",
            "--claim-id",
            "quant_claim_minimal_features",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["evidence"]["observed_metric"] == "1.0"
    assert data["evidence"]["verdict"] == "needs_review"


def test_agent_tool_cli_rejects_missing_required_options() -> None:
    result = runner.invoke(app, ["agent-tool", "validate-manifest"])

    assert result.exit_code == 1
    assert "--manifest is required" in result.output


def test_mcp_server_cli_reports_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_mcp_server(root: Path) -> None:
        raise McpDependencyError("Install it with: pip install -e '.[mcp]'")

    monkeypatch.setattr("claimbench.cli.run_mcp_server", fake_run_mcp_server)

    result = runner.invoke(app, ["mcp-server"])

    assert result.exit_code == 1
    assert "pip install -e" in result.output


def test_dashboard_cli_launches_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeDashboard:
        def launch(self, **kwargs: object) -> None:
            calls.append(kwargs)

    fake_module = types.ModuleType("claimbench.dashboard.app")

    def fake_build_app(root: Path) -> FakeDashboard:
        calls.append({"root": root})
        return FakeDashboard()

    fake_module.build_app = fake_build_app
    monkeypatch.setitem(sys.modules, "claimbench.dashboard.app", fake_module)

    result = runner.invoke(
        app,
        [
            "dashboard",
            "--root",
            "examples/manifests",
            "--host",
            "0.0.0.0",
            "--port",
            "7860",
            "--share",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        {"root": Path("examples/manifests")},
        {"server_name": "0.0.0.0", "server_port": 7860, "share": True},
    ]


def test_dashboard_cli_reports_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = types.ModuleType("claimbench.dashboard.app")

    def fake_build_app(root: Path) -> object:
        raise ImportError("No module named 'gradio'")

    fake_module.build_app = fake_build_app
    monkeypatch.setitem(sys.modules, "claimbench.dashboard.app", fake_module)

    result = runner.invoke(app, ["dashboard"])

    assert result.exit_code == 1
    assert "pip install -e '.[dashboard]'" in result.output
