"""Run artifact writing for ClaimBench experiment executions."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from claimbench.manifest import ClaimManifest
from claimbench.runner.executor import ExperimentRunResult
from claimbench.storage.cached_runs import build_cached_run_record


def write_run_artifacts(
    manifest: ClaimManifest,
    result: ExperimentRunResult,
    output_dir: Path,
    *,
    metric_output_path: Path | None = None,
) -> dict[str, Any]:
    """Write a run result, logs, and cache record to an artifact directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"
    cache_record_path = output_dir / "cache_record.json"

    result_path.write_text(
        json.dumps(asdict(result), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")

    cache_record = build_cached_run_record(
        manifest,
        result,
        artifact_uri=str(metric_output_path) if metric_output_path else str(result_path),
        log_uri=str(stdout_path),
    )
    cache_record_path.write_text(
        json.dumps(cache_record, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    return {
        "artifact_dir": str(output_dir),
        "result_path": str(result_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "cache_record_path": str(cache_record_path),
    }
