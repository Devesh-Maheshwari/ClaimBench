from __future__ import annotations

import json
import shutil
from pathlib import Path

from claimbench.manifest import load_manifest
from claimbench.runner.executor import run_manifest_experiment


def test_smoke_fixture_runs_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree("examples/fixtures/smoke_workspace", workspace)
    manifest = load_manifest(Path("examples/fixtures/manifests/smoke_test.manifest.json"))
    metric_output = workspace / "runs" / "smoke_metrics.json"

    result = run_manifest_experiment(
        manifest,
        "smoke_exp_accuracy",
        workspace=workspace,
        metric_output_path=metric_output,
    )

    assert result.status == "succeeded"
    assert result.observed_metric == 0.91
    assert result.verdicts[0].status == "reproduced"
    assert json.loads(metric_output.read_text(encoding="utf-8"))["accuracy"] == 0.91
