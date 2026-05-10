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


def build_app():
    """Build a Gradio Blocks app.

    Gradio is imported lazily so CLI and tests can use dashboard helpers without
    installing dashboard extras.
    """

    import gradio as gr

    store = LocalStore()
    choices = store.paper_ids()

    def select_paper(paper_id: str):
        summary = store.paper_summary(paper_id)
        rows = store.claim_rows(paper_id)
        claim_ids = [row[0] for row in rows]
        selected_claim = claim_ids[0] if claim_ids else None
        evidence = evidence_markdown(store.claim_evidence(paper_id, selected_claim))
        report = store.report_preview(paper_id)
        return summary, rows, gr.update(choices=claim_ids, value=selected_claim), evidence, report

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
        with gr.Tab("Overview"):
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
        with gr.Tab("Evidence"):
            claim_selector = gr.Dropdown(label="Claim", choices=[], value=None)
            evidence = gr.Markdown(label="Evidence")
        with gr.Tab("Report Preview"):
            report = gr.Markdown(label="Report Preview")

        selector.change(
            select_paper,
            inputs=selector,
            outputs=[summary, claims, claim_selector, evidence, report],
        )
        claim_selector.change(select_claim, inputs=[selector, claim_selector], outputs=evidence)
        if choices:
            demo.load(
                select_paper,
                inputs=selector,
                outputs=[summary, claims, claim_selector, evidence, report],
            )

    return demo


if __name__ == "__main__":
    build_app().launch()
