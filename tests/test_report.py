from __future__ import annotations

from pathlib import Path

from claimbench.manifest import ClaimManifest
from claimbench.report import (
    generate_reproducibility_report,
    report_to_dict,
    report_to_markdown,
)
from claimbench.runner.executor import ExperimentRunResult
from claimbench.runner.verdict import ClaimVerdict


def _manifest(tmp_path: Path) -> ClaimManifest:
    return ClaimManifest(
        path=tmp_path / "manifest.json",
        data={
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
                    "text": "The model reaches target accuracy.",
                    "claim_type": "numeric_metric",
                    "paper_location": "Table 1",
                    "expected_metric": {
                        "name": "accuracy",
                        "value": 0.9,
                        "unit": "accuracy",
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
                    "metric_parser": {"type": "json_path", "target": "$.accuracy"},
                    "linked_claim_ids": ["claim_accuracy"],
                }
            ],
        },
    )


def test_generate_reproducibility_report_without_runs(tmp_path: Path) -> None:
    report = generate_reproducibility_report(_manifest(tmp_path))
    markdown = report_to_markdown(report)

    assert report.summary["overall_status"] == "needs_review"
    assert report.summary["num_runs"] == 0
    assert report.claims[0].status == "executable"
    assert report.claims[0].observed_metric is None
    assert report.experiments[0].status == "not_run"
    assert "Claim status counts: `executable=1`" in markdown


def test_generate_reproducibility_report_with_reproduced_result(tmp_path: Path) -> None:
    result = ExperimentRunResult(
        experiment_id="exp_accuracy",
        status="succeeded",
        command=["python", "run.py"],
        returncode=0,
        runtime_seconds=1.2,
        stdout="done\n",
        stderr="",
        observed_metric=0.91,
        verdicts=[
            ClaimVerdict(
                status="reproduced",
                expected=0.9,
                observed=0.91,
                tolerance={"type": "absolute", "value": 0.02},
                reason="Observed metric is within tolerance.",
            )
        ],
    )

    report = generate_reproducibility_report(_manifest(tmp_path), [result])
    data = report_to_dict(report)
    markdown = report_to_markdown(report)

    assert report.summary["overall_status"] == "reproduced"
    assert report.claims[0].status == "reproduced"
    assert report.claims[0].observed_metric == 0.91
    assert data["experiments"][0]["runtime_seconds"] == 1.2
    assert "ClaimBench Report: Fixture Paper" in markdown
    assert "Claim status counts: `reproduced=1`" in markdown
    assert "Observed metric is within tolerance." in markdown


def test_generate_reproducibility_report_with_failed_run(tmp_path: Path) -> None:
    result = ExperimentRunResult(
        experiment_id="exp_accuracy",
        status="failed",
        command=["python", "run.py"],
        returncode=1,
        runtime_seconds=0.5,
        stdout="",
        stderr="boom",
        observed_metric=None,
        verdicts=[],
        error="Command exited with code 1.",
    )

    report = generate_reproducibility_report(_manifest(tmp_path), [result])

    assert report.summary["overall_status"] == "partial"
    assert report.claims[0].status == "failed"
    assert report.claims[0].reason == "Command exited with code 1."
    assert report.experiments[0].error == "Command exited with code 1."
