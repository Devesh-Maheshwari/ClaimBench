"""Cached run adapters for public demo data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from claimbench.manifest import ClaimManifest
from claimbench.runner.executor import ExperimentRunResult, _linked_claims
from claimbench.runner.verdict import compute_verdict


def load_cached_run_results(manifest: ClaimManifest) -> list[ExperimentRunResult]:
    """Convert manifest cached_runs entries into runner-compatible results."""

    experiments = {
        experiment["experiment_id"]: experiment
        for experiment in manifest.data.get("experiments", [])
    }
    results: list[ExperimentRunResult] = []
    for cached_run in manifest.data.get("cached_runs", []):
        experiment = experiments.get(cached_run["experiment_id"])
        if experiment is None:
            continue

        metrics = cached_run.get("metrics", {})
        observed = _observed_metric(metrics, experiment["metric_parser"])
        status = cached_run["status"]
        verdicts = []
        if status == "succeeded" and observed is not None:
            verdicts = [
                compute_verdict(claim, observed)
                for claim in _linked_claims(manifest, experiment["linked_claim_ids"])
            ]

        results.append(
            ExperimentRunResult(
                experiment_id=experiment["experiment_id"],
                status=status,
                command=list(experiment["command"]),
                returncode=0 if status == "succeeded" else None,
                runtime_seconds=_runtime_seconds(metrics),
                stdout="",
                stderr="",
                observed_metric=observed,
                verdicts=verdicts,
                error=None if status == "succeeded" else f"Cached run status: {status}",
            )
        )
    return results


def build_cached_run_record(
    manifest: ClaimManifest,
    result: ExperimentRunResult,
    *,
    run_id: str | None = None,
    artifact_uri: str | None = None,
    log_uri: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    """Build a manifest-compatible cached_runs record from a run result."""

    experiment = _experiment_by_id(manifest, result.experiment_id)
    metric_name = _metric_name(experiment["metric_parser"])
    metrics: dict[str, Any] = {
        metric_name: result.observed_metric,
        "runtime_seconds": result.runtime_seconds,
        "returncode": result.returncode,
    }
    if result.error is not None:
        metrics["error"] = result.error

    record: dict[str, Any] = {
        "run_id": run_id or _default_run_id(manifest.paper_id, result.experiment_id),
        "experiment_id": result.experiment_id,
        "status": _cached_status(result.status),
        "metrics": metrics,
        "log_uri": log_uri,
        "artifact_uris": [artifact_uri] if artifact_uri else [],
        "started_at": None,
        "finished_at": finished_at or datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    return record


def _observed_metric(metrics: dict[str, Any], parser: dict[str, str]) -> Any | None:
    parser_type = parser["type"]
    target = parser["target"]
    if parser_type == "json_path" and target.startswith("$."):
        current: Any = metrics
        for part in target[2:].split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current
    if parser_type == "csv_column":
        return metrics.get(target)
    if parser_type == "regex":
        return metrics.get(target)
    return None


def _experiment_by_id(manifest: ClaimManifest, experiment_id: str) -> dict[str, Any]:
    for experiment in manifest.data.get("experiments", []):
        if experiment["experiment_id"] == experiment_id:
            return experiment
    raise KeyError(f"Unknown experiment_id for {manifest.paper_id}: {experiment_id}")


def _metric_name(parser: dict[str, str]) -> str:
    parser_type = parser["type"]
    target = parser["target"]
    if parser_type == "json_path" and target.startswith("$."):
        return target[2:].split(".")[-1]
    return target


def _cached_status(status: str) -> str:
    if status in {"succeeded", "failed", "timed_out", "partial"}:
        return status
    return "succeeded"


def _default_run_id(paper_id: str, experiment_id: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{paper_id}_{experiment_id}_{timestamp}"


def _runtime_seconds(metrics: dict[str, Any]) -> float:
    value = metrics.get("runtime_seconds")
    if value is None:
        return 0.0
    return float(value)
