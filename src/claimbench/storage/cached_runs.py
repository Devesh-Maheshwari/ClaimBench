"""Cached run adapters for public demo data."""

from __future__ import annotations

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


def _runtime_seconds(metrics: dict[str, Any]) -> float:
    value = metrics.get("runtime_seconds")
    if value is None:
        return 0.0
    return float(value)
