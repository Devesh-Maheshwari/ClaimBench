"""Structured failure classification for experiment runs (deterministic heuristics)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

FailureType = Literal[
    "dependency_version_conflict",
    "missing_dataset",
    "missing_file",
    "command_failed",
    "metric_parse_failed",
    "timeout",
    "out_of_memory",
    "hardware_mismatch",
    "claim_metric_mismatch",
    "manual_review_required",
]

RepairRoute = Literal[
    "environment_agent",
    "data_agent",
    "repo_agent",
    "metric_parser",
    "supervisor",
    "experiment_planner",
    "end",
]


@dataclass(frozen=True)
class FailureClassification:
    failure_type: FailureType
    evidence: dict[str, Any]
    suggested_fix: str
    retryable: bool
    route_to: RepairRoute


def classify_failure(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int | None = None,
    status: str | None = None,
    error: str | None = None,
    missing_files: list[str] | None = None,
    parser_error: str | None = None,
    verdict_reason: str | None = None,
) -> FailureClassification:
    """Classify a failed run from logs, exit status, missing paths, and parser errors."""

    text = f"{stderr}\n{stdout}\n{error or ''}\n{parser_error or ''}"
    lower = text.lower()
    missing = missing_files or []

    if status == "timed_out":
        return FailureClassification(
            failure_type="timeout",
            evidence={"status": status, "snippet": _snippet(text)},
            suggested_fix="Increase timeout or reduce workload per supervisor policy.",
            retryable=True,
            route_to="supervisor",
        )

    if _matches_oom(lower):
        return FailureClassification(
            failure_type="out_of_memory",
            evidence={"status": status, "returncode": returncode, "snippet": _snippet(text)},
            suggested_fix="Raise Docker memory limit or use a smaller batch if policy allows.",
            retryable=True,
            route_to="environment_agent",
        )

    if _matches_hardware_mismatch(lower):
        return FailureClassification(
            failure_type="hardware_mismatch",
            evidence={"snippet": _snippet(text)},
            suggested_fix="Verify CPU/GPU/CUDA expectations vs manifest hardware_profile.",
            retryable=False,
            route_to="end",
        )

    if _matches_dependency_conflict(lower):
        pkg = _extract_package_conflict(lower)
        return FailureClassification(
            failure_type="dependency_version_conflict",
            evidence={"package_hint": pkg, "snippet": _snippet(text)},
            suggested_fix="Pin compatible versions in the audit Dockerfile or lockfile.",
            retryable=True,
            route_to="environment_agent",
        )

    if missing:
        if any("data" in m.lower() or "ucr" in m.lower() or "dataset" in m.lower() for m in missing):
            return FailureClassification(
                failure_type="missing_dataset",
                evidence={"missing_files": missing},
                suggested_fix="Run dataset preparation for your audit recipe (see claimbench.recipes) or fix dataset paths.",
                retryable=True,
                route_to="data_agent",
            )
        return FailureClassification(
            failure_type="missing_file",
            evidence={"missing_files": missing},
            suggested_fix="Restore missing inputs or correct paths in the manifest command.",
            retryable=True,
            route_to="data_agent",
        )

    if parser_error or (error and "metric" in (error or "").lower() and "parse" in (error or "").lower()):
        return FailureClassification(
            failure_type="metric_parse_failed",
            evidence={"parser_error": parser_error or error, "snippet": _snippet(text)},
            suggested_fix="Confirm metric output path and parser target (json_path/regex).",
            retryable=True,
            route_to="metric_parser",
        )

    if verdict_reason and _is_claim_mismatch_signal(verdict_reason, error):
        return FailureClassification(
            failure_type="claim_metric_mismatch",
            evidence={"verdict_reason": verdict_reason, "snippet": _snippet(text)},
            suggested_fix="Record scientific mismatch in the report; do not auto-change paper claims.",
            retryable=False,
            route_to="end",
        )

    if returncode not in (None, 0):
        if _matches_missing_module_or_file(lower):
            return FailureClassification(
                failure_type="missing_file",
                evidence={"returncode": returncode, "snippet": _snippet(text)},
                suggested_fix="Inspect repository layout and working directory; restore missing modules/files.",
                retryable=True,
                route_to="repo_agent",
            )
        return FailureClassification(
            failure_type="command_failed",
            evidence={"returncode": returncode, "snippet": _snippet(text)},
            suggested_fix="Re-check README entrypoints, arguments, and working directory.",
            retryable=True,
            route_to="repo_agent",
        )

    if status == "failed":
        if verdict_reason:
            return FailureClassification(
                failure_type="claim_metric_mismatch",
                evidence={"verdict_reason": verdict_reason, "snippet": _snippet(text)},
                suggested_fix="Record scientific mismatch in the report; do not auto-change paper claims.",
                retryable=False,
                route_to="end",
            )
        if _matches_missing_module_or_file(lower):
            return FailureClassification(
                failure_type="missing_file",
                evidence={"returncode": returncode, "snippet": _snippet(text)},
                suggested_fix="Inspect repository layout and working directory; restore missing modules/files.",
                retryable=True,
                route_to="repo_agent",
            )
        return FailureClassification(
            failure_type="command_failed",
            evidence={"returncode": returncode, "snippet": _snippet(text)},
            suggested_fix="Re-check README entrypoints, arguments, and working directory.",
            retryable=True,
            route_to="repo_agent",
        )

    return FailureClassification(
        failure_type="manual_review_required",
        evidence={"status": status, "returncode": returncode, "snippet": _snippet(text)},
        suggested_fix="Escalate to human review with captured logs and manifest.",
        retryable=False,
        route_to="end",
    )


def classification_to_dict(fc: FailureClassification) -> dict[str, Any]:
    return asdict(fc)


def propose_repair(fc: FailureClassification) -> dict[str, Any]:
    """Deterministic repair proposal from classification (does not mutate manifests)."""

    return {
        "failure_type": fc.failure_type,
        "route_to": fc.route_to,
        "retryable": fc.retryable,
        "suggested_fix": fc.suggested_fix,
        "evidence": fc.evidence,
        "safety_note": "Scientific claims in the manifest are not modified automatically.",
    }


def _snippet(text: str, max_len: int = 400) -> str:
    collapsed = " ".join(text.strip().split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3] + "..."


def _matches_oom(lower: str) -> bool:
    return any(
        p in lower
        for p in (
            "cannot allocate memory",
            "out of memory",
            "killed process",
            "cuda out of memory",
        )
    )


def _matches_hardware_mismatch(lower: str) -> bool:
    return any(
        p in lower
        for p in (
            "no cuda gpus are available",
            "cuda error: no cuda",
            "requires gpu",
        )
    )


def _matches_dependency_conflict(lower: str) -> bool:
    return any(
        p in lower
        for p in (
            "resolutionimpossible",
            "conflicting dependencies",
            "incompatible versions",
            "has no matching distribution",
            "could not find a version that satisfies",
        )
    )


def _extract_package_conflict(lower: str) -> str | None:
    m = re.search(r"package[s]?\s+['\"]?([a-z0-9_\-.]+)", lower)
    return m.group(1) if m else None


def _matches_missing_module_or_file(lower: str) -> bool:
    return (
        "modulenotfounderror" in lower
        or "no such file or directory" in lower
        or "filenotfounderror" in lower
    )


def _is_claim_mismatch_signal(verdict_reason: str, error: str | None) -> bool:
    v = verdict_reason.lower()
    if any(
        token in v
        for token in (
            "tolerance",
            "outside",
            "not reproduced",
            "observed metric",
        )
    ):
        return True
    if error and "verdict" in error.lower():
        return True
    return False
