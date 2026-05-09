"""Local read-only store used by the dashboard and early CLI workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claimbench.manifest import ClaimManifest, load_all_manifests
from claimbench.paths import EXAMPLE_MANIFESTS_ROOT
from claimbench.report import generate_reproducibility_report, report_to_markdown


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
        paper = manifest.data["paper"]
        claims = manifest.claims
        statuses = [claim["status"] for claim in claims]
        return {
            "paper_id": paper["paper_id"],
            "title": paper["title"],
            "arxiv_id": paper["arxiv_id"],
            "paper_url": paper.get("paper_url"),
            "repo_url": paper["repo_url"],
            "repo_commit": paper["repo_commit"],
            "domain": paper["domain"],
            "hardware_profile": paper.get("hardware_profile"),
            "num_claims": len(claims),
            "num_reproduced": statuses.count("reproduced"),
            "num_needs_review": statuses.count("needs_review"),
            "overall_status": _overall_status(statuses),
        }

    def claim_rows(self, paper_id: str) -> list[list[Any]]:
        manifest = self.get_manifest(paper_id)
        rows: list[list[Any]] = []
        for claim in manifest.claims:
            metric = claim["expected_metric"]
            rows.append(
                [
                    claim["claim_id"],
                    claim["status"],
                    claim["claim_type"],
                    claim["paper_location"],
                    _format_metric(metric),
                    ", ".join(claim.get("linked_experiment_ids", [])) or "unlinked",
                    claim["text"],
                ]
            )
        return rows

    def claim_evidence(self, paper_id: str, claim_id: str | None = None) -> ClaimEvidence:
        manifest = self.get_manifest(paper_id)
        claim = _select_claim(manifest, claim_id)
        experiments = _linked_experiments(manifest, claim)
        command = "not linked yet"
        if experiments:
            command = " ".join(experiments[0]["command"])

        return ClaimEvidence(
            claim_id=claim["claim_id"],
            experiment_ids=claim.get("linked_experiment_ids", []),
            expected_metric=_format_metric(claim["expected_metric"]),
            observed_metric="pending runner implementation",
            verdict=claim["status"],
            command=command,
            notes=(
                "This is manifest-level evidence. Week 3 will replace the "
                "placeholder observed metric with a sandboxed run result."
            ),
        )

    def report_preview(self, paper_id: str) -> str:
        manifest = self.get_manifest(paper_id)
        report = generate_reproducibility_report(manifest)
        return report_to_markdown(report)


def _format_metric(metric: dict[str, Any]) -> str:
    unit = metric.get("unit")
    suffix = f" {unit}" if unit else ""
    return f"{metric['name']}={metric['value']}{suffix}"


def _overall_status(statuses: list[str]) -> str:
    if not statuses:
        return "empty"
    if all(status == "reproduced" for status in statuses):
        return "reproduced"
    if any(status in {"failed", "partial"} for status in statuses):
        return "partial"
    return "needs_review"


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
