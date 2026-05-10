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
from claimbench.mcp_server import McpDependencyError, run_mcp_server
from claimbench.onboarding import init_paper_manifest
from claimbench.paths import SMOKE_MANIFEST_PATH, SMOKE_WORKSPACE_ROOT
from claimbench.report import generate_reproducibility_report, report_to_dict, report_to_markdown
from claimbench.repo_scanner import scan_repository
from claimbench.runner.artifacts import write_run_artifacts
from claimbench.runner.docker_runner import run_manifest_experiment_in_docker
from claimbench.runner.executor import run_manifest_experiment
from claimbench.storage.cached_runs import (
    build_cached_run_record,
    import_cached_run_record,
    load_cached_run_results,
)
from claimbench.storage.local_store import LocalStore
from claimbench.tools.local import (
    cached_report_tool,
    claim_evidence_tool,
    list_papers_tool,
    validate_manifest_tool,
)


app = typer.Typer(help="ClaimBench reproducibility auditor CLI.")
console = Console(width=240)


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
        store = LocalStore(root)
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title="ClaimBench Papers")
    table.add_column("Paper ID", no_wrap=True)
    table.add_column("Title", overflow="fold")
    table.add_column("Overall Status", no_wrap=True)
    table.add_column("Claims", justify="right")
    table.add_column("Cached Runs", justify="right")
    table.add_column("Failure Categories", no_wrap=True)
    table.add_column("Manifest", overflow="fold")

    for row in store.paper_catalog_rows():
        paper_id = row[0]
        manifest = store.get_manifest(paper_id)
        try:
            manifest_display = str(manifest.path.relative_to(root))
        except ValueError:
            manifest_display = str(manifest.path)
        table.add_row(
            row[0],
            row[1],
            row[2],
            str(row[3]),
            str(row[4]),
            row[7],
            manifest_display,
        )
    console.print(table)


@app.command("show-paper")
def show_paper(
    path: Annotated[Path, typer.Argument(help="Path to a ClaimManifest JSON file.")],
    use_cached_runs: Annotated[
        bool,
        typer.Option("--cached-runs/--no-cached-runs", help="Include manifest cached_runs in the summary."),
    ] = True,
) -> None:
    """Show a compact paper and claim summary from a manifest."""

    try:
        manifest = load_manifest(path)
        run_results = load_cached_run_results(manifest) if use_cached_runs else []
        generated = generate_reproducibility_report(manifest, run_results)
    except (ManifestError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    paper = manifest.data["paper"]
    console.print(f"[bold]{paper['title']}[/bold]")
    console.print(f"Paper ID: {paper['paper_id']}")
    console.print(f"arXiv: {paper['arxiv_id']}")
    console.print(f"Repo: {paper['repo_url']} @ {paper['repo_commit']}")
    console.print(f"Overall status: {generated.summary['overall_status']}")
    console.print(f"Claim status counts: {_format_counts_for_cli(generated.summary['status_counts'])}")
    console.print(
        f"Experiment status counts: "
        f"{_format_counts_for_cli(generated.summary['experiment_status_counts'])}"
    )
    console.print(
        f"Failure category counts: "
        f"{_format_counts_for_cli(generated.summary['failure_category_counts'])}"
    )

    console.print("[bold]Claims[/bold]")
    for claim in generated.claims:
        observed = str(claim.observed_metric) if claim.observed_metric is not None else "not run"
        experiments = ", ".join(claim.linked_experiment_ids) or "none"
        console.print(
            f"- {claim.claim_id}: {claim.status} | "
            f"expected {_format_metric_for_cli(claim.expected_metric)} | "
            f"observed {observed} | experiments {experiments}"
        )
        console.print(f"  {claim.text}")


def _format_metric_for_cli(metric: dict[str, object]) -> str:
    name = metric.get("name", "metric")
    value = metric.get("value", "unknown")
    return f"{name}={value}"


def _format_counts_for_cli(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


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
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional file path to write the rendered report."),
    ] = None,
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
        rendered = report_to_markdown(generated)
    elif output_format == "json":
        rendered = json.dumps(report_to_dict(generated), indent=2, default=str)
    else:
        console.print(f"[red]Unsupported report format: {output_format}. Expected 'markdown' or 'json'.[/red]")
        raise typer.Exit(1)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        console.print(f"[green]Report written:[/green] {output}")
        return

    if output_format == "json":
        print(rendered)
    else:
        console.print(rendered)


@app.command("export-reports")
def export_reports(
    root: Annotated[
        Path,
        typer.Option("--root", help="Directory containing *.manifest.json files."),
    ] = Path("examples/manifests"),
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory to write generated reports."),
    ] = Path("examples/reports"),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Report output format: markdown or json."),
    ] = "markdown",
    use_cached_runs: Annotated[
        bool,
        typer.Option("--cached-runs/--no-cached-runs", help="Include manifest cached_runs in reports."),
    ] = True,
) -> None:
    """Render reproducibility reports for every manifest in a directory."""

    extension_by_format = {"markdown": "md", "json": "json"}
    if output_format not in extension_by_format:
        console.print(f"[red]Unsupported report format: {output_format}. Expected 'markdown' or 'json'.[/red]")
        raise typer.Exit(1)

    try:
        manifests = load_all_manifests(root)
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    if not manifests:
        console.print(f"[yellow]No manifests found in {root}[/yellow]")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for manifest in manifests:
        run_results = load_cached_run_results(manifest) if use_cached_runs else []
        generated = generate_reproducibility_report(manifest, run_results)
        if output_format == "markdown":
            rendered = report_to_markdown(generated)
        else:
            rendered = json.dumps(report_to_dict(generated), indent=2, default=str)

        output_path = output_dir / f"{manifest.paper_id}.{extension_by_format[output_format]}"
        output_path.write_text(rendered + "\n", encoding="utf-8")
        written.append(output_path)

    console.print(f"[green]Reports written:[/green] {len(written)}")
    for path in written:
        console.print(f"- {path}")


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


@app.command("mcp-server")
def mcp_server(
    root: Annotated[
        Path,
        typer.Option("--root", help="Directory containing *.manifest.json files."),
    ] = Path("examples/manifests"),
) -> None:
    """Run the ClaimBench MCP server over stdio."""

    try:
        run_mcp_server(root)
    except McpDependencyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command("dashboard")
def dashboard(
    root: Annotated[
        Path,
        typer.Option("--root", help="Directory containing *.manifest.json files."),
    ] = Path("examples/manifests"),
    host: Annotated[
        str,
        typer.Option("--host", help="Server host for the Gradio dashboard."),
    ] = "127.0.0.1",
    port: Annotated[
        int | None,
        typer.Option("--port", help="Server port for the Gradio dashboard."),
    ] = None,
    share: Annotated[
        bool,
        typer.Option("--share", help="Create a public Gradio share link."),
    ] = False,
) -> None:
    """Launch the local Gradio dashboard."""

    try:
        from claimbench.dashboard.app import build_app

        build_app(root).launch(server_name=host, server_port=port, share=share)
    except ImportError as exc:
        console.print(
            "Dashboard dependencies are not installed.\n"
            "Install them with: pip install -e '.[dashboard]'",
            markup=False,
        )
        raise typer.Exit(1) from exc


@app.command("import-cache-record")
def import_cache_record(
    manifest_path: Annotated[Path, typer.Argument(help="Path to a ClaimManifest JSON file.")],
    record_path: Annotated[Path, typer.Argument(help="Path to a cached run record JSON file.")],
    replace: Annotated[
        bool,
        typer.Option("--replace", help="Replace an existing cached run with the same run_id."),
    ] = False,
) -> None:
    """Import a cached run record into a manifest cached_runs list."""

    try:
        result = import_cached_run_record(manifest_path, record_path, replace=replace)
    except (ManifestError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    print(json.dumps(result, indent=2, default=str))


@app.command("smoke-test")
def smoke_test(
    artifact_dir: Annotated[
        Path,
        typer.Option("--artifact-dir", help="Directory to write smoke test artifacts."),
    ] = Path("runs/smoke_cli"),
) -> None:
    """Run the built-in fixture through the local runner and artifact writer."""

    try:
        manifest = load_manifest(SMOKE_MANIFEST_PATH)
        metric_output = SMOKE_WORKSPACE_ROOT / "runs" / "smoke_metrics.json"
        result = run_manifest_experiment(
            manifest,
            "smoke_exp_accuracy",
            workspace=SMOKE_WORKSPACE_ROOT,
            metric_output_path=metric_output,
        )
        artifact_summary = write_run_artifacts(
            manifest,
            result,
            artifact_dir,
            metric_output_path=metric_output,
        )
    except (ManifestError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[green]Smoke test status:[/green] {result.status}")
    console.print(json.dumps(artifact_summary, indent=2, default=str))
    console.print(json.dumps(asdict(result), indent=2, default=str))
    if result.status in {"failed", "timed_out"}:
        raise typer.Exit(1)


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
    cache_record_output: Annotated[
        Path | None,
        typer.Option(
            "--cache-record-output",
            help="Optional path to write a manifest cached_runs record for this run.",
        ),
    ] = None,
    artifact_dir: Annotated[
        Path | None,
        typer.Option(
            "--artifact-dir",
            help="Optional directory to write result.json, stdout/stderr logs, and cache_record.json.",
        ),
    ] = None,
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

    if cache_record_output is not None:
        record = build_cached_run_record(
            manifest,
            result,
            artifact_uri=str(metric_output) if metric_output else None,
        )
        cache_record_output.parent.mkdir(parents=True, exist_ok=True)
        cache_record_output.write_text(
            json.dumps(record, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        console.print(f"[green]Cached run record written:[/green] {cache_record_output}")

    if artifact_dir is not None:
        artifact_summary = write_run_artifacts(
            manifest,
            result,
            artifact_dir,
            metric_output_path=metric_output,
        )
        console.print(f"[green]Run artifacts written:[/green] {artifact_dir}")
        console.print(json.dumps(artifact_summary, indent=2, default=str))

    console.print(json.dumps(asdict(result), indent=2, default=str))
    if result.status in {"failed", "timed_out"}:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
