"""Generic manifest-driven experiment execution."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claimbench.manifest import ClaimManifest
from claimbench.runner.metrics import MetricParseError, parse_metric
from claimbench.runner.verdict import ClaimVerdict, compute_verdict


@dataclass(frozen=True)
class ExperimentRunResult:
    """Result of a manifest experiment execution."""

    experiment_id: str
    status: str
    command: list[str]
    returncode: int | None
    runtime_seconds: float
    stdout: str
    stderr: str
    observed_metric: Any | None
    verdicts: list[ClaimVerdict]
    error: str | None = None


def run_manifest_experiment(
    manifest: ClaimManifest,
    experiment_id: str,
    *,
    workspace: Path,
    metric_output_path: Path | None = None,
    timeout_seconds: int = 300,
) -> ExperimentRunResult:
    """Run an experiment from a manifest in a local workspace."""

    experiment = _find_experiment(manifest, experiment_id)
    command = list(experiment["command"])
    working_directory = workspace / experiment.get("working_directory", ".")

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=working_directory,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        runtime = time.monotonic() - started
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="timed_out",
            command=command,
            returncode=None,
            runtime_seconds=runtime,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            observed_metric=None,
            verdicts=[],
            error=f"Timed out after {timeout_seconds} seconds.",
        )
    except OSError as exc:
        runtime = time.monotonic() - started
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="failed",
            command=command,
            returncode=None,
            runtime_seconds=runtime,
            stdout="",
            stderr="",
            observed_metric=None,
            verdicts=[],
            error=str(exc),
        )

    runtime = time.monotonic() - started
    if completed.returncode != 0:
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="failed",
            command=command,
            returncode=completed.returncode,
            runtime_seconds=runtime,
            stdout=completed.stdout,
            stderr=completed.stderr,
            observed_metric=None,
            verdicts=[],
            error=f"Command exited with code {completed.returncode}.",
        )

    try:
        observed = parse_metric(
            experiment["metric_parser"],
            stdout=completed.stdout,
            output_path=metric_output_path,
        )
        verdicts = [
            compute_verdict(claim, observed)
            for claim in _linked_claims(manifest, experiment["linked_claim_ids"])
        ]
    except (MetricParseError, ValueError) as exc:
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="failed",
            command=command,
            returncode=completed.returncode,
            runtime_seconds=runtime,
            stdout=completed.stdout,
            stderr=completed.stderr,
            observed_metric=None,
            verdicts=[],
            error=str(exc),
        )

    status = "succeeded"
    if any(verdict.status == "failed" for verdict in verdicts):
        status = "failed"
    elif any(verdict.status == "needs_review" for verdict in verdicts):
        status = "needs_review"

    return ExperimentRunResult(
        experiment_id=experiment_id,
        status=status,
        command=command,
        returncode=completed.returncode,
        runtime_seconds=runtime,
        stdout=completed.stdout,
        stderr=completed.stderr,
        observed_metric=observed,
        verdicts=verdicts,
        error=None,
    )


def _find_experiment(manifest: ClaimManifest, experiment_id: str) -> dict[str, Any]:
    for experiment in manifest.data.get("experiments", []):
        if experiment["experiment_id"] == experiment_id:
            return experiment
    raise KeyError(f"Unknown experiment_id for {manifest.paper_id}: {experiment_id}")


def _linked_claims(manifest: ClaimManifest, claim_ids: list[str]) -> list[dict[str, Any]]:
    claim_by_id = {claim["claim_id"]: claim for claim in manifest.claims}
    return [claim_by_id[claim_id] for claim_id in claim_ids if claim_id in claim_by_id]
