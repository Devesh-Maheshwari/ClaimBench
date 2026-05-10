"""Local read-only store used by the dashboard and early CLI workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claimbench.manifest import ClaimManifest, load_all_manifests
from claimbench.paths import EXAMPLE_MANIFESTS_ROOT
from claimbench.report import generate_reproducibility_report, report_to_markdown
from claimbench.storage.cached_runs import load_cached_run_results


@dataclass(frozen=True)
class ClaimEvidence:
    """Dashboard-ready evidence for a claim before the runner exists."""

    claim_id: str
    experiment_ids: list[str]
    expected_metric: str
    observed_metric: str
    verdict: str
    command: str
    notes: str


class LocalStore:
    """Loads manifests and exposes dashboard-friendly read models."""

    def __init__(self, manifest_root: Path = EXAMPLE_MANIFESTS_ROOT) -> None:
        self.manifest_root = manifest_root
        self._manifests = load_all_manifests(manifest_root)
        self._by_id = {manifest.paper_id: manifest for manifest in self._manifests}

    @property
    def manifests(self) -> list[ClaimManifest]:
        return list(self._manifests)

    def paper_ids(self) -> list[str]:
        return sorted(self._by_id)

    def get_manifest(self, paper_id: str) -> ClaimManifest:
        return self._by_id[paper_id]

    def paper_summary(self, paper_id: str) -> dict[str, Any]:
        manifest = self.get_manifest(paper_id)
        report = generate_reproducibility_report(manifest, load_cached_run_results(manifest))
        paper = manifest.data["paper"]
        statuses = [claim.status for claim in report.claims]
        return {
            "paper_id": paper["paper_id"],
            "title": paper["title"],
            "arxiv_id": paper["arxiv_id"],
            "paper_url": paper.get("paper_url"),
            "repo_url": paper["repo_url"],
            "repo_commit": paper["repo_commit"],
            "domain": paper["domain"],
            "hardware_profile": paper.get("hardware_profile"),
            "num_claims": len(report.claims),
            "num_cached_runs": report.summary["num_runs"],
            "num_reproduced": statuses.count("reproduced"),
            "num_needs_review": statuses.count("needs_review"),
            "overall_status": report.summary["overall_status"],
        }

    def claim_rows(self, paper_id: str) -> list[list[Any]]:
        manifest = self.get_manifest(paper_id)
        report = generate_reproducibility_report(manifest, load_cached_run_results(manifest))
        report_by_claim = {claim.claim_id: claim for claim in report.claims}
        rows: list[list[Any]] = []
        for claim in manifest.claims:
            claim_report = report_by_claim[claim["claim_id"]]
            metric = claim["expected_metric"]
            rows.append(
                [
                    claim["claim_id"],
                    claim_report.status,
                    claim["claim_type"],
                    claim["paper_location"],
                    _format_metric(metric),
                    claim_report.observed_metric if claim_report.observed_metric is not None else "not run",
                    ", ".join(claim.get("linked_experiment_ids", [])) or "unlinked",
                    claim["text"],
                ]
            )
        return rows

    def experiment_rows(self, paper_id: str) -> list[list[Any]]:
        manifest = self.get_manifest(paper_id)
        report = generate_reproducibility_report(manifest, load_cached_run_results(manifest))
        experiments_by_id = {
            experiment["experiment_id"]: experiment
            for experiment in manifest.data.get("experiments", [])
        }
        rows: list[list[Any]] = []
        for experiment in report.experiments:
            manifest_experiment = experiments_by_id[experiment.experiment_id]
            rows.append(
                [
                    experiment.experiment_id,
                    manifest_experiment["name"],
                    experiment.status,
                    experiment.observed_metric if experiment.observed_metric is not None else "not run",
                    experiment.runtime_seconds
                    if experiment.runtime_seconds is not None
                    else "not run",
                    ", ".join(manifest_experiment.get("linked_claim_ids", [])) or "unlinked",
                    " ".join(experiment.command),
                ]
            )
        return rows

    def environment_summary(self, paper_id: str) -> dict[str, Any]:
        manifest = self.get_manifest(paper_id)
        environment = manifest.data.get("environment", {})
        return {
            "execution_mode": environment.get("execution_mode", "unknown"),
            "base_image": environment.get("base_image") or "not specified",
            "python_version": environment.get("python_version") or "not specified",
            "cuda_version": environment.get("cuda_version") or "not required",
            "dependency_files": environment.get("dependency_files", []),
            "image_digest": environment.get("image_digest") or "not pinned",
        }

    def dataset_rows(self, paper_id: str) -> list[list[Any]]:
        manifest = self.get_manifest(paper_id)
        rows: list[list[Any]] = []
        for dataset in manifest.data.get("datasets", []):
            rows.append(
                [
                    dataset["dataset_id"],
                    dataset["name"],
                    dataset["source"],
                    dataset.get("version") or "not specified",
                    dataset.get("sha256") or "not pinned",
                    dataset.get("access_notes") or "",
                ]
            )
        return rows

    def review_status(self, paper_id: str) -> dict[str, Any]:
        manifest = self.get_manifest(paper_id)
        provenance = manifest.data.get("provenance", {})
        validation = manifest.data.get("validation", {})
        return {
            "review_status": provenance.get("review_status", "unknown"),
            "created_by": provenance.get("created_by", "unknown"),
            "created_at": provenance.get("created_at", "unknown"),
            "extraction_model": provenance.get("extraction_model") or "manual",
            "parser_version": provenance.get("parser_version") or "not specified",
            "manual_edits": provenance.get("manual_edits", []),
            "unresolved_fields": validation.get("unresolved_fields", []),
            "validation_notes": validation.get("notes", ""),
        }

    def local_commands(self, paper_id: str) -> dict[str, str]:
        manifest = self.get_manifest(paper_id)
        manifest_path = _display_path(manifest.path)
        return {
            "validate": f"claimbench validate {manifest_path}",
            "markdown_report": f"claimbench report {manifest_path} --format markdown",
            "json_report": f"claimbench report {manifest_path} --format json",
            "cached_evidence": (
                "claimbench agent-tool claim-evidence "
                f"--manifest-path {manifest_path} --paper-id {paper_id}"
            ),
        }

    def claim_evidence(self, paper_id: str, claim_id: str | None = None) -> ClaimEvidence:
        manifest = self.get_manifest(paper_id)
        claim = _select_claim(manifest, claim_id)
        report = generate_reproducibility_report(manifest, load_cached_run_results(manifest))
        claim_report = _select_claim_report(report.claims, claim["claim_id"])
        experiments = _linked_experiments(manifest, claim)
        command = "not linked yet"
        if experiments:
            command = " ".join(experiments[0]["command"])

        return ClaimEvidence(
            claim_id=claim["claim_id"],
            experiment_ids=claim.get("linked_experiment_ids", []),
            expected_metric=_format_metric(claim["expected_metric"]),
            observed_metric=str(claim_report.observed_metric)
            if claim_report.observed_metric is not None
            else "not run",
            verdict=claim_report.status,
            command=command,
            notes=claim_report.reason,
        )

    def report_preview(self, paper_id: str) -> str:
        manifest = self.get_manifest(paper_id)
        report = generate_reproducibility_report(manifest, load_cached_run_results(manifest))
        return report_to_markdown(report)


def _format_metric(metric: dict[str, Any]) -> str:
    unit = metric.get("unit")
    suffix = f" {unit}" if unit else ""
    return f"{metric['name']}={metric['value']}{suffix}"


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _overall_status(statuses: list[str]) -> str:
    if not statuses:
        return "empty"
    if all(status == "reproduced" for status in statuses):
        return "reproduced"
    if any(status in {"failed", "partial"} for status in statuses):
        return "partial"
    return "needs_review"


def _select_claim_report(claim_reports: list[Any], claim_id: str) -> Any:
    for claim_report in claim_reports:
        if claim_report.claim_id == claim_id:
            return claim_report
    raise KeyError(f"Unknown claim report: {claim_id}")


def _select_claim(manifest: ClaimManifest, claim_id: str | None) -> dict[str, Any]:
    claims = manifest.claims
    if not claims:
        raise ValueError(f"Manifest has no claims: {manifest.paper_id}")
    if claim_id is None:
        return claims[0]
    for claim in claims:
        if claim["claim_id"] == claim_id:
            return claim
    raise KeyError(f"Unknown claim_id for {manifest.paper_id}: {claim_id}")


def _linked_experiments(
    manifest: ClaimManifest,
    claim: dict[str, Any],
) -> list[dict[str, Any]]:
    linked = set(claim.get("linked_experiment_ids", []))
    return [
        experiment
        for experiment in manifest.data.get("experiments", [])
        if experiment["experiment_id"] in linked
    ]
