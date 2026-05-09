"""Command-line interface for ClaimBench."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from claimbench.manifest import (
    ManifestError,
    discover_manifests,
    load_all_manifests,
    load_manifest,
    load_json,
    validate_manifest_data,
)
from claimbench.onboarding import init_paper_manifest
from claimbench.report import generate_reproducibility_report, report_to_dict, report_to_markdown
from claimbench.repo_scanner import scan_repository
from claimbench.runner.docker_runner import run_manifest_experiment_in_docker
from claimbench.runner.executor import run_manifest_experiment
from claimbench.storage.cached_runs import load_cached_run_results
from claimbench.tools.local import (
    cached_report_tool,
    claim_evidence_tool,
    list_papers_tool,
    validate_manifest_tool,
)


app = typer.Typer(help="ClaimBench reproducibility auditor CLI.")
console = Console()


@app.command("validate-manifest")
def validate_manifest(
    path: Annotated[Path, typer.Argument(help="Path to a ClaimManifest JSON file.")],
) -> None:
    """Validate a ClaimManifest against the project schema."""

    try:
        data = load_json(path)
        issues = validate_manifest_data(data)
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    if issues:
        console.print(f"[red]Manifest validation failed: {path}[/red]")
        for issue in issues:
            console.print(f"  - [bold]{issue.path}[/bold]: {issue.message}")
        raise typer.Exit(1)

    console.print(f"[green]Manifest is valid:[/green] {path}")


@app.command("list-papers")
def list_papers(
    root: Annotated[
        Path,
        typer.Option("--root", help="Directory containing *.manifest.json files."),
    ] = Path("examples/manifests"),
) -> None:
    """List known papers from manifest files."""

    paths = discover_manifests(root)
    if not paths:
        console.print(f"[yellow]No manifests found in {root}[/yellow]")
        return

    try:
        manifests = load_all_manifests(root)
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title="ClaimBench Papers")
    table.add_column("Paper ID")
    table.add_column("Title")
    table.add_column("Claims", justify="right")
    table.add_column("Manifest")

    for manifest in manifests:
        table.add_row(
            manifest.paper_id,
            manifest.title,
            str(len(manifest.claims)),
            str(manifest.path),
        )
    console.print(table)


@app.command("show-paper")
def show_paper(
    path: Annotated[Path, typer.Argument(help="Path to a ClaimManifest JSON file.")],
) -> None:
    """Show a compact paper and claim summary from a manifest."""

    try:
        manifest = load_manifest(path)
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    paper = manifest.data["paper"]
    console.print(f"[bold]{paper['title']}[/bold]")
    console.print(f"Paper ID: {paper['paper_id']}")
    console.print(f"arXiv: {paper['arxiv_id']}")
    console.print(f"Repo: {paper['repo_url']} @ {paper['repo_commit']}")

    table = Table(title="Claims")
    table.add_column("Claim ID")
    table.add_column("Status")
    table.add_column("Expected Metric")
    table.add_column("Text")

    for claim in manifest.claims:
        metric = claim["expected_metric"]
        table.add_row(
            claim["claim_id"],
            claim["status"],
            f"{metric['name']}={metric['value']}",
            claim["text"],
        )
    console.print(table)


@app.command("scan-repo")
def scan_repo(
    path: Annotated[Path, typer.Argument(help="Path to a local repository.")],
) -> None:
    """Scan a local repository for setup files and candidate entrypoints."""

    result = scan_repository(path)
    console.print(result.to_json())


@app.command("init-paper")
def init_paper(
    arxiv_id: Annotated[str, typer.Option("--arxiv-id", help="Paper arXiv ID.")],
    repo_url: Annotated[str, typer.Option("--repo-url", help="Paper code repository URL.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output manifest path.")],
    commit: Annotated[str | None, typer.Option("--commit", help="Optional repository commit SHA.")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Optional paper title.")] = None,
) -> None:
    """Create a draft manifest skeleton for a new paper."""

    manifest = init_paper_manifest(
        arxiv_id=arxiv_id,
        repo_url=repo_url,
        output_path=output,
        commit=commit,
        title=title,
    )
    console.print(f"[green]Draft manifest written:[/green] {manifest}")


@app.command("report")
def report(
    manifest_path: Annotated[Path, typer.Argument(help="Path to a ClaimManifest JSON file.")],
    output_format: Annotated[
        str,
        typer.Option("--format", help="Report output format: markdown or json."),
    ] = "markdown",
    use_cached_runs: Annotated[
        bool,
        typer.Option("--cached-runs/--no-cached-runs", help="Include manifest cached_runs in the report."),
    ] = True,
) -> None:
    """Render a reproducibility report from a manifest."""

    try:
        manifest = load_manifest(manifest_path)
        run_results = load_cached_run_results(manifest) if use_cached_runs else []
        generated = generate_reproducibility_report(manifest, run_results)
    except (ManifestError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    if output_format == "markdown":
        console.print(report_to_markdown(generated))
    elif output_format == "json":
        print(json.dumps(report_to_dict(generated), indent=2, default=str))
    else:
        console.print(f"[red]Unsupported report format: {output_format}. Expected 'markdown' or 'json'.[/red]")
        raise typer.Exit(1)


@app.command("agent-tool")
def agent_tool(
    tool_name: Annotated[
        str,
        typer.Argument(help="Tool name: list-papers, validate-manifest, claim-evidence, or cached-report."),
    ],
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Manifest path for validate-manifest or cached-report."),
    ] = None,
    paper_id: Annotated[
        str | None,
        typer.Option("--paper-id", help="Paper ID for claim-evidence or cached-report."),
    ] = None,
    claim_id: Annotated[
        str | None,
        typer.Option("--claim-id", help="Optional claim ID for claim-evidence."),
    ] = None,
    root: Annotated[
        Path,
        typer.Option("--root", help="Directory containing *.manifest.json files."),
    ] = Path("examples/manifests"),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Report output format for cached-report: json or markdown."),
    ] = "json",
) -> None:
    """Run a read-only local agent tool and print JSON."""

    try:
        if tool_name == "list-papers":
            payload = list_papers_tool(root)
        elif tool_name == "validate-manifest":
            if manifest_path is None:
                raise ValueError("--manifest is required for validate-manifest.")
            payload = validate_manifest_tool(manifest_path)
        elif tool_name == "claim-evidence":
            if paper_id is None:
                raise ValueError("--paper-id is required for claim-evidence.")
            payload = claim_evidence_tool(paper_id, claim_id=claim_id, manifest_root=root)
        elif tool_name == "cached-report":
            payload = cached_report_tool(
                paper_id=paper_id,
                manifest_path=manifest_path,
                manifest_root=root,
                output_format=output_format,
            )
        else:
            raise ValueError(f"Unsupported agent tool: {tool_name}.")
    except (ManifestError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    print(json.dumps(payload, indent=2, default=str))


@app.command("run-experiment")
def run_experiment(
    manifest_path: Annotated[Path, typer.Argument(help="Path to a ClaimManifest JSON file.")],
    experiment_id: Annotated[str, typer.Argument(help="Experiment ID to execute.")],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Workspace where the command should run."),
    ] = Path("."),
    metric_output: Annotated[
        Path | None,
        typer.Option("--metric-output", help="Metric file used by json_path/csv_column parsers."),
    ] = None,
    timeout_seconds: Annotated[
        int,
        typer.Option("--timeout-seconds", help="Maximum runtime before cancellation."),
    ] = 300,
    sandbox: Annotated[
        str,
        typer.Option("--sandbox", help="Execution sandbox: local or docker."),
    ] = "local",
    docker_image: Annotated[
        str | None,
        typer.Option("--docker-image", help="Docker image for --sandbox docker."),
    ] = None,
    docker_network: Annotated[
        str,
        typer.Option("--docker-network", help="Docker network mode for --sandbox docker."),
    ] = "none",
    docker_memory: Annotated[
        str,
        typer.Option("--docker-memory", help="Docker memory limit for --sandbox docker."),
    ] = "4g",
    docker_cpus: Annotated[
        str,
        typer.Option("--docker-cpus", help="Docker CPU limit for --sandbox docker."),
    ] = "2",
) -> None:
    """Run a manifest experiment and print the captured result."""

    try:
        manifest = load_manifest(manifest_path)
        if sandbox == "local":
            result = run_manifest_experiment(
                manifest,
                experiment_id,
                workspace=workspace,
                metric_output_path=metric_output,
                timeout_seconds=timeout_seconds,
            )
        elif sandbox == "docker":
            result = run_manifest_experiment_in_docker(
                manifest,
                experiment_id,
                workspace=workspace,
                image=docker_image or manifest.data["environment"]["base_image"],
                metric_output_path=metric_output,
                timeout_seconds=timeout_seconds,
                network=docker_network,
                memory=docker_memory,
                cpus=docker_cpus,
            )
        else:
            raise ValueError(f"Unsupported sandbox: {sandbox}. Expected 'local' or 'docker'.")
    except (ManifestError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(json.dumps(asdict(result), indent=2, default=str))
    if result.status in {"failed", "timed_out"}:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
