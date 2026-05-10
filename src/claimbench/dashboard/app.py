"""Gradio dashboard scaffold for the ClaimBench public demo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claimbench.manifest import ClaimManifest
from claimbench.storage.local_store import ClaimEvidence, LocalStore


def load_dashboard_manifests(root: Path = Path("examples/manifests")) -> list[ClaimManifest]:
    """Load manifests for dashboard rendering."""

    return LocalStore(root).manifests


def paper_choices(manifests: list[ClaimManifest]) -> list[str]:
    """Return dropdown choices as stable paper IDs."""

    return [manifest.paper_id for manifest in manifests]


def paper_summary(manifest: ClaimManifest) -> dict[str, Any]:
    """Return serializable paper summary data for the dashboard."""

    paper = manifest.data["paper"]
    return {
        "paper_id": paper["paper_id"],
        "title": paper["title"],
        "arxiv_id": paper["arxiv_id"],
        "repo_url": paper["repo_url"],
        "repo_commit": paper["repo_commit"],
        "domain": paper["domain"],
        "num_claims": len(manifest.claims),
    }


def claims_rows(manifest: ClaimManifest) -> list[list[Any]]:
    """Return claim table rows."""

    rows: list[list[Any]] = []
    for claim in manifest.claims:
        metric = claim["expected_metric"]
        rows.append(
            [
                claim["claim_id"],
                claim["status"],
                claim["claim_type"],
                claim["paper_location"],
                f"{metric['name']}={metric['value']}",
                claim["text"],
            ]
        )
    return rows


def claim_choices(manifest: ClaimManifest) -> list[str]:
    """Return claim IDs for a paper."""

    return [claim["claim_id"] for claim in manifest.claims]


def overview_markdown(summary: dict[str, Any]) -> str:
    """Render a readable paper overview."""

    paper_url = summary.get("paper_url") or f"https://arxiv.org/abs/{summary['arxiv_id']}"
    failure_counts = _format_counts(summary["failure_category_counts"])
    return "\n".join(
        [
            f"## {summary['title']}",
            "",
            f"- Paper ID: `{summary['paper_id']}`",
            f"- Overall status: `{summary['overall_status']}`",
            f"- Claims: `{summary['num_claims']}`",
            f"- Cached demo runs: `{summary['num_cached_runs']}`",
            f"- Needs review: `{summary['num_needs_review']}`",
            f"- Reproduced: `{summary['num_reproduced']}`",
            f"- Failure categories: `{failure_counts}`",
            f"- arXiv: [{summary['arxiv_id']}]({paper_url})",
            f"- Repository: [{summary['repo_url']}]({summary['repo_url']})",
            f"- Commit: `{summary['repo_commit']}`",
            "",
            "This public demo shows curated cached runs for safety. "
            "Local/self-hosted runs can execute manifests in a sandbox and import generated cache records.",
        ]
    )


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def environment_markdown(environment: dict[str, Any]) -> str:
    """Render environment requirements for a paper."""

    dependency_files = ", ".join(environment["dependency_files"]) or "none listed"
    return "\n".join(
        [
            "## Environment",
            "",
            f"- Execution mode: `{environment['execution_mode']}`",
            f"- Base image: `{environment['base_image']}`",
            f"- Python: `{environment['python_version']}`",
            f"- CUDA: `{environment['cuda_version']}`",
            f"- Dependency files: `{dependency_files}`",
            f"- Image digest: `{environment['image_digest']}`",
        ]
    )


def review_status_markdown(review: dict[str, Any]) -> str:
    """Render manifest review and validation status."""

    manual_edits = "\n".join(f"- {edit}" for edit in review["manual_edits"]) or "- none listed"
    unresolved_fields = (
        "\n".join(f"- {field}" for field in review["unresolved_fields"]) or "- none listed"
    )
    return "\n".join(
        [
            "## Review Status",
            "",
            f"- Status: `{review['review_status']}`",
            f"- Created by: `{review['created_by']}`",
            f"- Created at: `{review['created_at']}`",
            f"- Extraction model: `{review['extraction_model']}`",
            f"- Parser version: `{review['parser_version']}`",
            "",
            "### Manual Edits",
            "",
            manual_edits,
            "",
            "### Unresolved Fields",
            "",
            unresolved_fields,
            "",
            "### Validation Notes",
            "",
            review["validation_notes"] or "No validation notes listed.",
        ]
    )


def local_commands_markdown(commands: dict[str, str]) -> str:
    """Render copy-ready local commands for the selected paper."""

    return "\n\n".join(
        [
            "## Local Commands",
            "Validate the manifest:",
            f"```bash\n{commands['validate']}\n```",
            "Show the paper summary with cached runs:",
            f"```bash\n{commands['show_paper']}\n```",
            "Show the paper summary without cached runs:",
            f"```bash\n{commands['show_paper_without_cached_runs']}\n```",
            "Generate a Markdown report:",
            f"```bash\n{commands['markdown_report']}\n```",
            "Generate machine-readable JSON:",
            f"```bash\n{commands['json_report']}\n```",
            "Export reports for all manifests in this dashboard root:",
            f"```bash\n{commands['export_reports']}\n```",
            "Inspect cached claim evidence through the agent-tool interface:",
            f"```bash\n{commands['cached_evidence']}\n```",
        ]
    )


def evidence_markdown(evidence: ClaimEvidence) -> str:
    """Render claim evidence as markdown."""

    return "\n".join(
        [
            f"## Evidence for `{evidence.claim_id}`",
            "",
            f"- Verdict: `{evidence.verdict}`",
            f"- Expected metric: `{evidence.expected_metric}`",
            f"- Observed metric: `{evidence.observed_metric}`",
            f"- Linked experiments: `{', '.join(evidence.experiment_ids) or 'none'}`",
            "",
            "### Command",
            "",
            "```text",
            evidence.command,
            "```",
            "",
            "### Notes",
            "",
            evidence.notes,
        ]
    )


def build_app(manifest_root: Path = Path("examples/manifests")):
    """Build a Gradio Blocks app.

    Gradio is imported lazily so CLI and tests can use dashboard helpers without
    installing dashboard extras.
    """

    import gradio as gr

    store = LocalStore(manifest_root)
    choices = store.paper_ids()

    def select_paper(paper_id: str):
        summary = store.paper_summary(paper_id)
        overview = overview_markdown(summary)
        rows = store.claim_rows(paper_id)
        experiment_rows = store.experiment_rows(paper_id)
        cached_runs = store.cached_run_rows(paper_id)
        environment = environment_markdown(store.environment_summary(paper_id))
        datasets = store.dataset_rows(paper_id)
        review = review_status_markdown(store.review_status(paper_id))
        local_commands = local_commands_markdown(store.local_commands(paper_id))
        claim_ids = [row[0] for row in rows]
        selected_claim = claim_ids[0] if claim_ids else None
        evidence = evidence_markdown(store.claim_evidence(paper_id, selected_claim))
        report = store.report_preview(paper_id)
        return (
            overview,
            summary,
            rows,
            experiment_rows,
            cached_runs,
            environment,
            datasets,
            review,
            local_commands,
            gr.update(choices=claim_ids, value=selected_claim),
            evidence,
            report,
        )

    def select_claim(paper_id: str, claim_id: str):
        return evidence_markdown(store.claim_evidence(paper_id, claim_id))

    with gr.Blocks(title="ClaimBench") as demo:
        gr.Markdown(
            "# ClaimBench\n"
            "Claim-level reproducibility auditor for selected ML papers.\n\n"
            "This public demo starts with cached/manifest-level evidence. "
            "The runner phase adds sandboxed execution, parsed metrics, logs, and artifacts."
        )
        selector = gr.Dropdown(choices=choices, label="Paper", value=choices[0] if choices else None)
        with gr.Tab("Paper Catalog"):
            gr.Dataframe(
                value=store.paper_catalog_rows(),
                headers=[
                    "Paper ID",
                    "Title",
                    "Overall Status",
                    "Claims",
                    "Cached Runs",
                    "Reproduced",
                    "Needs Review",
                    "Failure Categories",
                    "Repository",
                ],
                label="Paper Catalog",
                interactive=False,
            )
        with gr.Tab("Overview"):
            overview = gr.Markdown(label="Overview")
            summary = gr.JSON(label="Paper Summary")
        with gr.Tab("Claims"):
            claims = gr.Dataframe(
                headers=[
                    "Claim ID",
                    "Status",
                    "Type",
                    "Paper Location",
                    "Expected Metric",
                    "Observed Metric",
                    "Linked Experiments",
                    "Claim",
                ],
                label="Claims",
                interactive=False,
            )
        with gr.Tab("Experiments"):
            experiments = gr.Dataframe(
                headers=[
                    "Experiment ID",
                    "Name",
                    "Status",
                    "Failure Category",
                    "Observed Metric",
                    "Runtime Seconds",
                    "Linked Claims",
                    "Command",
                ],
                label="Experiments",
                interactive=False,
            )
        with gr.Tab("Cached Runs"):
            cached_runs = gr.Dataframe(
                headers=[
                    "Run ID",
                    "Experiment ID",
                    "Status",
                    "Metrics",
                    "Log URI",
                    "Artifact URIs",
                    "Started At",
                    "Finished At",
                ],
                label="Cached Runs",
                interactive=False,
            )
        with gr.Tab("Resources"):
            environment = gr.Markdown(label="Environment")
            datasets = gr.Dataframe(
                headers=[
                    "Dataset ID",
                    "Name",
                    "Source",
                    "Version",
                    "SHA256",
                    "Access Notes",
                ],
                label="Datasets",
                interactive=False,
            )
        with gr.Tab("Review Status"):
            review = gr.Markdown(label="Review Status")
        with gr.Tab("Local Commands"):
            local_commands = gr.Markdown(label="Local Commands")
        with gr.Tab("Evidence"):
            claim_selector = gr.Dropdown(label="Claim", choices=[], value=None)
            evidence = gr.Markdown(label="Evidence")
        with gr.Tab("Report Preview"):
            report = gr.Markdown(label="Report Preview")

        selector.change(
            select_paper,
            inputs=selector,
            outputs=[
                overview,
                summary,
                claims,
                experiments,
                cached_runs,
                environment,
                datasets,
                review,
                local_commands,
                claim_selector,
                evidence,
                report,
            ],
        )
        claim_selector.change(select_claim, inputs=[selector, claim_selector], outputs=evidence)
        if choices:
            demo.load(
                select_paper,
                inputs=selector,
                outputs=[
                    overview,
                    summary,
                    claims,
                    experiments,
                    cached_runs,
                    environment,
                    datasets,
                    review,
                    local_commands,
                    claim_selector,
                    evidence,
                    report,
                ],
            )

    return demo


if __name__ == "__main__":
    build_app().launch()
