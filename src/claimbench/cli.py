"""Command-line interface for ClaimBench."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from claimbench.agents.audit_graph import run_agent_audit
from claimbench.audit import AuditRecipeError, prepare_audit_manifest, prepare_ucr_dataset
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


@app.command("audit-paper")
def audit_paper(
    paper_url: Annotated[str, typer.Option("--paper-url", help="Paper URL, e.g. arXiv abstract URL.")],
    code_url: Annotated[str, typer.Option("--code-url", help="Official code repository URL.")],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory for audit workspace and artifacts."),
    ],
    dataset: Annotated[
        str,
        typer.Option("--dataset", help="Dataset name for the supported audit recipe."),
    ] = "Coffee",
    num_kernels: Annotated[
        int,
        typer.Option("--num-kernels", help="ROCKET kernels for the first audit run."),
    ] = 1000,
    code_commit: Annotated[
        str | None,
        typer.Option("--code-commit", help="Optional repository commit to checkout."),
    ] = None,
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Workspace mounted/executed by run-paper."),
    ] = Path("."),
    timeout_seconds: Annotated[
        int,
        typer.Option("--timeout-seconds", help="Maximum runtime per experiment before cancellation."),
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
    run: Annotated[
        bool,
        typer.Option("--run/--prepare-only", help="Run the generated manifest after preparation."),
    ] = True,
    clone_repo: Annotated[
        bool,
        typer.Option("--clone-repo/--skip-clone", help="Clone/fetch the official code repository."),
    ] = True,
    cleanup_workspace: Annotated[
        bool,
        typer.Option("--cleanup-workspace", help="Delete the cloned code workspace after the audit."),
    ] = False,
    cleanup_docker_image: Annotated[
        bool,
        typer.Option(
            "--cleanup-docker-image",
            help="Remove the Docker image after the audit. Containers are already removed with docker --rm.",
        ),
    ] = False,
    prepare_data: Annotated[
        bool,
        typer.Option(
            "--prepare-data/--skip-data-prep",
            help="Download/extract required public dataset files before running.",
        ),
    ] = True,
) -> None:
    """Prepare and optionally run a supported paper audit from paper/code URLs."""

    try:
        prepared = prepare_audit_manifest(
            paper_url=paper_url,
            code_url=code_url,
            output_dir=output_dir,
            dataset=dataset,
            num_kernels=num_kernels,
            code_commit=code_commit,
            clone_repo=clone_repo,
        )
    except AuditRecipeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    manifest_path = prepared["manifest_path"]
    console.print(f"[green]Audit manifest written:[/green] {manifest_path}")
    console.print(f"[green]Code workspace:[/green] {prepared['repo_dir']}")
    if prepared["scan_path"] is not None:
        console.print(f"[green]Repository scan written:[/green] {prepared['scan_path']}")
    if not run:
        return

    if prepare_data:
        try:
            console.print(f"[bold]Preparing dataset:[/bold] UCR {dataset}")
            data_summary = prepare_ucr_dataset(output_dir=output_dir, dataset=dataset)
            console.print(f"[green]Dataset ready:[/green] {data_summary['dataset_dir']}")
        except AuditRecipeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc

    exit_code = 0
    try:
        run_paper(
            manifest_path=manifest_path,
            workspace=workspace,
            output_dir=output_dir / "run",
            timeout_seconds=timeout_seconds,
            sandbox=sandbox,
            docker_image=docker_image,
            docker_network=docker_network,
            docker_memory=docker_memory,
            docker_cpus=docker_cpus,
            fail_fast=False,
        )
    except typer.Exit as exc:
        exit_code = int(exc.exit_code or 1)
    finally:
        if cleanup_workspace:
            shutil.rmtree(prepared["repo_dir"], ignore_errors=True)
            console.print(f"[yellow]Cleaned code workspace:[/yellow] {prepared['repo_dir']}")
        if cleanup_docker_image and sandbox == "docker":
            image = docker_image or "python:3.10-slim"
            subprocess.run(["docker", "image", "rm", image], check=False)
            console.print(f"[yellow]Requested Docker image cleanup:[/yellow] {image}")

    if exit_code:
        raise typer.Exit(exit_code)


@app.command("agent-audit")
def agent_audit(
    paper_url: Annotated[str, typer.Option("--paper-url", help="Paper URL, e.g. arXiv abstract URL.")],
    code_url: Annotated[str, typer.Option("--code-url", help="Official code repository URL.")],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory for audit workspace, trace, and run artifacts."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Workspace mounted/executed by experiments."),
    ] = Path("."),
    dataset: Annotated[
        str,
        typer.Option("--dataset", help="Dataset name for the supported audit recipe."),
    ] = "Coffee",
    num_kernels: Annotated[
        int,
        typer.Option("--num-kernels", help="ROCKET kernels for the audit run."),
    ] = 1000,
    code_commit: Annotated[
        str | None,
        typer.Option("--code-commit", help="Optional repository commit to checkout."),
    ] = None,
    timeout_seconds: Annotated[
        int,
        typer.Option("--timeout-seconds", help="Maximum runtime per experiment."),
    ] = 300,
    sandbox: Annotated[
        str,
        typer.Option("--sandbox", help="Execution sandbox: local or docker (CPU path)."),
    ] = "docker",
    execution_mode: Annotated[
        str,
        typer.Option(
            "--execution-mode",
            help="cpu: local/docker executor; gpu: non-blocking remote stub (trace only).",
        ),
    ] = "cpu",
    max_retries: Annotated[
        int,
        typer.Option("--max-retries", help="Bounded repair retries (no silent claim edits)."),
    ] = 3,
    docker_image: Annotated[
        str | None,
        typer.Option("--docker-image", help="Docker image for --sandbox docker."),
    ] = None,
    docker_network: Annotated[
        str,
        typer.Option("--docker-network", help="Docker network mode."),
    ] = "none",
    docker_memory: Annotated[
        str,
        typer.Option("--docker-memory", help="Docker memory limit."),
    ] = "4g",
    docker_cpus: Annotated[
        str,
        typer.Option("--docker-cpus", help="Docker CPU limit."),
    ] = "2",
    prepare_data: Annotated[
        bool,
        typer.Option("--prepare-data/--skip-data-prep", help="Download/extract UCR dataset files."),
    ] = True,
    clone_repo: Annotated[
        bool,
        typer.Option("--clone-repo/--skip-clone", help="Clone/fetch the official code repository."),
    ] = True,
    trace_file: Annotated[
        Path | None,
        typer.Option("--trace-file", help="Optional path for audit_trace.json (default: output_dir/audit_trace.json)."),
    ] = None,
) -> None:
    """Run the multi-agent audit graph (deterministic supervisor; writes audit_trace.json)."""

    backend = "remote_gpu" if execution_mode == "gpu" else "local_docker"
    if execution_mode not in {"cpu", "gpu"}:
        console.print("[red]execution-mode must be cpu or gpu[/red]")
        raise typer.Exit(1)
    try:
        state = run_agent_audit(
            paper_url=paper_url,
            code_url=code_url,
            output_dir=output_dir,
            workspace=workspace,
            dataset=dataset,
            num_kernels=num_kernels,
            code_commit=code_commit,
            sandbox=sandbox,
            execution_backend=backend,  # type: ignore[arg-type]
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            docker_image=docker_image,
            docker_network=docker_network,
            docker_memory=docker_memory,
            docker_cpus=docker_cpus,
            prepare_data=prepare_data,
            clone_repo=clone_repo,
            trace_path=trace_file,
        )
    except AuditRecipeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    trace_out = trace_file or (output_dir / "audit_trace.json")
    console.print(f"[green]Audit trace:[/green] {trace_out}")
    console.print(f"[green]Status:[/green] {state.get('status')}")
    if state.get("final_report_path"):
        console.print(f"[green]Report:[/green] {state['final_report_path']}")

    st = state.get("status")
    if st in {"failed"}:
        raise typer.Exit(1)
    if st == "submitted_remote":
        raise typer.Exit(0)


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


@app.command("run-paper")
def run_paper(
    manifest_path: Annotated[Path, typer.Argument(help="Path to a ClaimManifest JSON file.")],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Workspace where experiment commands should run."),
    ] = Path("."),
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory to write paper run artifacts."),
    ] = Path("runs/paper"),
    timeout_seconds: Annotated[
        int,
        typer.Option("--timeout-seconds", help="Maximum runtime per experiment before cancellation."),
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
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop after the first failed or timed-out experiment."),
    ] = False,
) -> None:
    """Run every experiment in a manifest and write paper-level artifacts."""

    try:
        manifest = load_manifest(manifest_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        artifact_summaries = []

        for experiment in manifest.data.get("experiments", []):
            experiment_id = experiment["experiment_id"]
            metric_output = _infer_metric_output_path(workspace, experiment)
            console.print(f"[bold]Running experiment:[/bold] {experiment_id}")
            console.print(f"- Sandbox: {sandbox}")
            console.print(f"- Command: {' '.join(str(part) for part in experiment['command'])}")
            console.print(f"- Metric output: {metric_output if metric_output is not None else 'stdout parser'}")
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

            results.append(result)
            artifact_summary = write_run_artifacts(
                manifest,
                result,
                output_dir / "experiments" / experiment_id,
                metric_output_path=metric_output,
            )
            artifact_summaries.append(artifact_summary)
            console.print(f"[green]{experiment_id}:[/green] {result.status}")
            console.print(f"- Runtime seconds: {result.runtime_seconds:.3f}")
            console.print(
                f"- Observed metric: "
                f"{result.observed_metric if result.observed_metric is not None else 'not parsed'}"
            )
            for verdict in result.verdicts:
                console.print(
                    f"- Verdict: {verdict.status} "
                    f"(expected={verdict.expected}, observed={verdict.observed})"
                )
            if result.error:
                console.print(f"[red]- Error:[/red] {result.error}")
            if result.stdout.strip():
                console.print(f"- Stdout: {_one_line(result.stdout)}")
            if result.stderr.strip():
                console.print(f"- Stderr: {_one_line(result.stderr)}")
            console.print(f"- Artifacts: {artifact_summary['artifact_dir']}")
            if fail_fast and result.status in {"failed", "timed_out"}:
                break

        report = generate_reproducibility_report(manifest, results)
        report_json_path = output_dir / "report.json"
        report_markdown_path = output_dir / "report.md"
        summary_path = output_dir / "run_summary.json"
        report_json_path.write_text(
            json.dumps(report_to_dict(report), indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        report_markdown_path.write_text(report_to_markdown(report) + "\n", encoding="utf-8")
        summary_path.write_text(
            json.dumps(
                {
                    "paper_id": manifest.paper_id,
                    "manifest_path": str(manifest_path),
                    "sandbox": sandbox,
                    "num_experiments": len(manifest.data.get("experiments", [])),
                    "num_completed": len(results),
                    "overall_status": report.summary["overall_status"],
                    "experiment_status_counts": report.summary["experiment_status_counts"],
                    "failure_category_counts": report.summary["failure_category_counts"],
                    "artifacts": artifact_summaries,
                    "report_json_path": str(report_json_path),
                    "report_markdown_path": str(report_markdown_path),
                },
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
    except (ManifestError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[green]Paper run artifacts written:[/green] {output_dir}")
    console.print(f"Overall status: {report.summary['overall_status']}")
    console.print(f"Report JSON: {report_json_path}")
    console.print(f"Report Markdown: {report_markdown_path}")
    if any(result.status in {"failed", "timed_out"} for result in results):
        raise typer.Exit(1)


def _infer_metric_output_path(workspace: Path, experiment: dict[str, object]) -> Path | None:
    parser = experiment.get("metric_parser")
    if not isinstance(parser, dict) or parser.get("type") == "regex":
        return None

    command = experiment.get("command", [])
    if not isinstance(command, list):
        return None
    for index, token in enumerate(command[:-1]):
        if token == "--output":
            output_path = Path(str(command[index + 1]))
            return output_path if output_path.is_absolute() else workspace / output_path
    return None


def _one_line(text: str, *, max_length: int = 240) -> str:
    collapsed = " ".join(text.strip().split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3] + "..."


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
