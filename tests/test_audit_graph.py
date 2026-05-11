from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from claimbench.agents.audit_graph import run_agent_audit


def _write_manifest(path: Path) -> None:
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
                "datasets": [{"dataset_id": "d1", "name": "D", "source": "synthetic"}],
                "provenance": {"created_by": "test", "created_at": "2026-01-01", "review_status": "draft"},
            }
        ),
        encoding="utf-8",
    )


@patch("claimbench.agents.audit_graph.prepare_ucr_dataset")
@patch("claimbench.agents.audit_graph.prepare_audit_manifest")
def test_agent_audit_writes_trace_and_parallel_inspect(mock_manifest, mock_data, tmp_path: Path) -> None:
    mock_data.return_value = {"status": "extracted", "dataset": "Coffee"}
    out = tmp_path / "audit_out"
    out.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest_path = out / "manifest.json"
    scan_path = out / "repo_scan.json"
    _write_manifest(manifest_path)
    scan_path.write_text(json.dumps({"setup_files": []}), encoding="utf-8")
    mock_manifest.return_value = {
        "manifest_path": manifest_path,
        "repo_dir": repo,
        "scan_path": scan_path,
    }
    ucr = out / "data" / "UCR" / "Coffee"
    ucr.mkdir(parents=True)
    (ucr / "Coffee_TRAIN.tsv").write_text("1\t0\n", encoding="utf-8")
    (ucr / "Coffee_TEST.tsv").write_text("2\t0\n", encoding="utf-8")
    ws = tmp_path / "workspace"
    ws.mkdir()

    state = run_agent_audit(
        paper_url="https://arxiv.org/abs/1910.13051",
        code_url="https://github.com/angus924/rocket",
        output_dir=out,
        workspace=ws,
        dataset="Coffee",
        sandbox="local",
        execution_backend="local_docker",
        max_retries=1,
        prepare_data=True,
        clone_repo=True,
        timeout_seconds=60,
    )

    trace_path = out / "audit_trace.json"
    assert trace_path.is_file()
    phases = [e["phase"] for e in state["graph_trace"]]
    assert "initialize" in phases
    assert "parallel_inspect" in phases
    assert "merge_manifest" in phases
    assert "executor" in phases
    assert state["branch_traces"]["paper"]["agent"] == "paper"


@patch("claimbench.agents.audit_graph.prepare_ucr_dataset")
@patch("claimbench.agents.audit_graph.prepare_audit_manifest")
def test_agent_audit_gpu_stub_stops_async(mock_manifest, mock_data, tmp_path: Path) -> None:
    mock_data.return_value = {"status": "skipped"}
    out = tmp_path / "audit_gpu"
    out.mkdir()
    repo = tmp_path / "repo2"
    repo.mkdir()
    manifest_path = out / "manifest.json"
    scan_path = out / "scan.json"
    _write_manifest(manifest_path)
    scan_path.write_text("{}", encoding="utf-8")
    mock_manifest.return_value = {
        "manifest_path": manifest_path,
        "repo_dir": repo,
        "scan_path": scan_path,
    }
    ws = tmp_path / "ws2"
    ws.mkdir()

    state = run_agent_audit(
        paper_url="u",
        code_url="c",
        output_dir=out,
        workspace=ws,
        prepare_data=False,
        clone_repo=False,
        sandbox="local",
        execution_backend="remote_gpu",
    )
    assert state["status"] == "submitted_remote"
    assert state["remote_run_handles"]
