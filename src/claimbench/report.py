"""Reproducibility report generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from claimbench.manifest import ClaimManifest
from claimbench.runner.executor import ExperimentRunResult


@dataclass(frozen=True)
class ClaimReport:
    """Report row for a paper claim."""

    claim_id: str
    text: str
    expected_metric: dict[str, Any]
    observed_metric: Any | None
    status: str
    reason: str
    linked_experiment_ids: list[str]


@dataclass(frozen=True)
class ExperimentReport:
    """Report row for an experiment run."""

    experiment_id: str
    status: str
    command: list[str]
    returncode: int | None
    runtime_seconds: float | None
    observed_metric: Any | None
    failure_category: str
    error: str | None


@dataclass(frozen=True)
class ReproducibilityReport:
    """Serializable claim-level reproducibility report."""

    paper: dict[str, Any]
    summary: dict[str, Any]
    claims: list[ClaimReport]
    experiments: list[ExperimentReport]


def generate_reproducibility_report(
    manifest: ClaimManifest,
    run_results: list[ExperimentRunResult] | None = None,
) -> ReproducibilityReport:
    """Generate a report from a manifest and optional experiment results."""

    results = {result.experiment_id: result for result in run_results or []}
    claim_reports = [
        _claim_report(manifest, claim, results)
        for claim in manifest.claims
    ]
    experiment_reports = [
        _experiment_report(experiment, results.get(experiment["experiment_id"]))
        for experiment in manifest.data.get("experiments", [])
    ]
    status_counts = _status_counts([claim.status for claim in claim_reports])
    experiment_status_counts = _status_counts(
        [experiment.status for experiment in experiment_reports]
    )

    return ReproducibilityReport(
        paper=dict(manifest.data["paper"]),
        summary={
            "paper_id": manifest.paper_id,
            "title": manifest.title,
            "num_claims": len(claim_reports),
            "num_experiments": len(experiment_reports),
            "num_runs": len(results),
            "status_counts": status_counts,
            "experiment_status_counts": experiment_status_counts,
            "overall_status": _overall_status([claim.status for claim in claim_reports]),
        },
        claims=claim_reports,
        experiments=experiment_reports,
    )


def report_to_dict(report: ReproducibilityReport) -> dict[str, Any]:
    """Convert a report dataclass tree to plain Python data."""

    return asdict(report)


def report_to_markdown(report: ReproducibilityReport) -> str:
    """Render a reproducibility report as Markdown."""

    summary = report.summary
    paper = report.paper
    lines = [
        f"# ClaimBench Report: {paper['title']}",
        "",
        f"- Paper ID: `{paper['paper_id']}`",
        f"- arXiv: `{paper['arxiv_id']}`",
        f"- Repository: `{paper['repo_url']}`",
        f"- Commit: `{paper['repo_commit']}`",
        f"- Overall status: `{summary['overall_status']}`",
        f"- Claims: `{summary['num_claims']}`",
        f"- Experiment runs: `{summary['num_runs']}`",
        f"- Claim status counts: `{_format_status_counts(summary['status_counts'])}`",
        f"- Experiment status counts: `{_format_status_counts(summary['experiment_status_counts'])}`",
        "",
        "## Claims",
    ]

    for claim in report.claims:
        lines.extend(
            [
                "",
                f"### `{claim.claim_id}`",
                "",
                f"- Status: `{claim.status}`",
                f"- Expected: `{_format_metric(claim.expected_metric)}`",
                f"- Observed: `{claim.observed_metric if claim.observed_metric is not None else 'not run'}`",
                f"- Experiments: `{', '.join(claim.linked_experiment_ids) or 'none'}`",
                f"- Reason: {claim.reason}",
                "",
                claim.text,
            ]
        )

    lines.extend(["", "## Experiments"])
    for experiment in report.experiments:
        lines.extend(
            [
                "",
                f"### `{experiment.experiment_id}`",
                "",
                f"- Status: `{experiment.status}`",
                f"- Return code: `{experiment.returncode if experiment.returncode is not None else 'n/a'}`",
                f"- Runtime seconds: `{experiment.runtime_seconds if experiment.runtime_seconds is not None else 'not run'}`",
                f"- Observed metric: `{experiment.observed_metric if experiment.observed_metric is not None else 'not run'}`",
                f"- Failure category: `{experiment.failure_category}`",
                f"- Command: `{' '.join(experiment.command)}`",
            ]
        )
        if experiment.error:
            lines.append(f"- Error: {experiment.error}")

    return "\n".join(lines)


def _claim_report(
    manifest: ClaimManifest,
    claim: dict[str, Any],
    results: dict[str, ExperimentRunResult],
) -> ClaimReport:
    linked_ids = claim.get("linked_experiment_ids", [])
    for experiment in manifest.data.get("experiments", []):
        experiment_id = experiment["experiment_id"]
        if experiment_id not in linked_ids or experiment_id not in results:
            continue
        result = results[experiment_id]
        if result.status in {"failed", "timed_out"} and not result.verdicts:
            return ClaimReport(
                claim_id=claim["claim_id"],
                text=claim["text"],
                expected_metric=claim["expected_metric"],
                observed_metric=result.observed_metric,
                status=result.status,
                reason=result.error or "Experiment did not complete successfully.",
                linked_experiment_ids=linked_ids,
            )

        verdict = _linked_verdict(experiment, claim["claim_id"], result)
        if verdict is not None:
            return ClaimReport(
                claim_id=claim["claim_id"],
                text=claim["text"],
                expected_metric=claim["expected_metric"],
                observed_metric=verdict.observed,
                status=verdict.status,
                reason=verdict.reason,
                linked_experiment_ids=linked_ids,
            )

    return ClaimReport(
        claim_id=claim["claim_id"],
        text=claim["text"],
        expected_metric=claim["expected_metric"],
        observed_metric=None,
        status=claim["status"],
        reason="No run result is available for this claim yet.",
        linked_experiment_ids=linked_ids,
    )


def _linked_verdict(
    experiment: dict[str, Any],
    claim_id: str,
    result: ExperimentRunResult,
) -> Any | None:
    for index, linked_claim_id in enumerate(experiment["linked_claim_ids"]):
        if linked_claim_id == claim_id and index < len(result.verdicts):
            return result.verdicts[index]
    return None


def _experiment_report(
    experiment: dict[str, Any],
    result: ExperimentRunResult | None,
) -> ExperimentReport:
    if result is None:
        return ExperimentReport(
            experiment_id=experiment["experiment_id"],
            status="not_run",
            command=list(experiment["command"]),
            returncode=None,
            runtime_seconds=None,
            observed_metric=None,
            failure_category="not_run",
            error=None,
        )

    return ExperimentReport(
        experiment_id=result.experiment_id,
        status=result.status,
        command=list(result.command),
        returncode=result.returncode,
        runtime_seconds=result.runtime_seconds,
        observed_metric=result.observed_metric,
        failure_category=_failure_category(result),
        error=result.error,
    )


def _status_counts(statuses: list[str]) -> dict[str, int]:
    return {status: statuses.count(status) for status in sorted(set(statuses))}


def _failure_category(result: ExperimentRunResult) -> str:
    if result.status in {"succeeded", "needs_review"}:
        return "none"
    if result.status == "timed_out":
        return "timeout"
    if result.returncode not in {None, 0}:
        return "command_failed"
    if result.error:
        lowered = result.error.lower()
        if "metric" in lowered or "parse" in lowered:
            return "metric_parse_failed"
        if "no such file" in lowered or "not found" in lowered:
            return "missing_file"
    if result.status == "failed":
        return "runner_failed"
    return result.status


def _overall_status(statuses: list[str]) -> str:
    if not statuses:
        return "empty"
    if all(status == "reproduced" for status in statuses):
        return "reproduced"
    if any(status in {"failed", "timed_out", "partial"} for status in statuses):
        return "partial"
    return "needs_review"


def _format_status_counts(status_counts: dict[str, int]) -> str:
    if not status_counts:
        return "none"
    return ", ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))


def _format_metric(metric: dict[str, Any]) -> str:
    unit = metric.get("unit")
    suffix = f" {unit}" if unit else ""
    return f"{metric['name']}={metric['value']}{suffix}"
