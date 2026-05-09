from __future__ import annotations

import json
import sys
from pathlib import Path

from claimbench.manifest import ClaimManifest
from claimbench.runner.executor import run_manifest_experiment
from claimbench.runner.metrics import parse_metric
from claimbench.runner.verdict import compute_verdict


def test_parse_metric_from_regex() -> None:
    value = parse_metric({"type": "regex", "target": r"accuracy=([0-9.]+)"}, stdout="accuracy=0.91")

    assert value == "0.91"


def test_parse_metric_from_json_path(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"accuracy": 0.92}), encoding="utf-8")

    value = parse_metric({"type": "json_path", "target": "$.accuracy"}, stdout="", output_path=metrics)

    assert value == 0.92


def test_compute_verdict_absolute_reproduced() -> None:
    claim = {
        "expected_metric": {"value": 0.9},
        "tolerance": {"type": "absolute", "value": 0.05},
    }

    verdict = compute_verdict(claim, 0.92)

    assert verdict.status == "reproduced"


def test_run_manifest_experiment_with_json_metric(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    script = tmp_path / "write_metrics.py"
    script.write_text(
        "import json\n"
        f"open({str(metrics)!r}, 'w', encoding='utf-8').write(json.dumps({{'accuracy': 0.91}}))\n"
        "print('done')\n",
        encoding="utf-8",
    )
    manifest = ClaimManifest(
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
                    "command": [sys.executable, str(script)],
                    "working_directory": ".",
                    "metric_parser": {"type": "json_path", "target": "$.accuracy"},
                    "linked_claim_ids": ["claim_accuracy"],
                }
            ],
        },
    )

    result = run_manifest_experiment(
        manifest,
        "exp_accuracy",
        workspace=tmp_path,
        metric_output_path=metrics,
    )

    assert result.status == "reproduced" or result.status == "succeeded"
    assert result.observed_metric == 0.91
    assert result.verdicts[0].status == "reproduced"
