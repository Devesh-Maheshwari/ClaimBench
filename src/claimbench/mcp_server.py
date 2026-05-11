"""MCP server wrapper for ClaimBench agent tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claimbench.paths import EXAMPLE_MANIFESTS_ROOT
from claimbench.tools.local import (
    cached_report_tool,
    claim_evidence_tool,
    list_papers_tool,
    validate_manifest_tool,
)
from claimbench.tools.audit_mcp import (
    classify_failure_tool,
    get_audit_report as audit_get_report,
    get_audit_status as audit_get_status,
    get_audit_trace as audit_get_trace,
    propose_repair_tool,
    start_audit as audit_start,
)


class McpDependencyError(RuntimeError):
    """Raised when the optional MCP dependency is not installed."""


def create_mcp_server(manifest_root: Path = EXAMPLE_MANIFESTS_ROOT) -> Any:
    """Create a FastMCP server exposing ClaimBench read-only tools."""

    fast_mcp = _load_fastmcp()
    server = fast_mcp("claimbench")

    @server.tool()
    def list_papers() -> dict[str, Any]:
        """List curated ClaimBench papers and cached-run summaries."""

        return list_papers_tool(manifest_root)

    @server.tool()
    def validate_manifest(path: str) -> dict[str, Any]:
        """Validate a ClaimManifest JSON file."""

        return validate_manifest_tool(Path(path))

    @server.tool()
    def claim_evidence(paper_id: str, claim_id: str | None = None) -> dict[str, Any]:
        """Return cached evidence for a paper claim."""

        return claim_evidence_tool(
            paper_id,
            claim_id=claim_id,
            manifest_root=manifest_root,
        )

    @server.tool()
    def cached_report(
        paper_id: str | None = None,
        manifest_path: str | None = None,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """Return a cached reproducibility report as JSON or Markdown."""

        return cached_report_tool(
            paper_id=paper_id,
            manifest_path=Path(manifest_path) if manifest_path else None,
            manifest_root=manifest_root,
            output_format=output_format,
        )

    @server.tool()
    def start_audit(
        paper_url: str,
        code_url: str,
        output_dir: str,
        workspace: str | None = None,
        dataset: str = "Coffee",
        sandbox: str = "docker",
        execution_mode: str = "cpu",
        max_retries: int = 3,
        timeout_seconds: int = 300,
        prepare_data: bool = True,
        clone_repo: bool = True,
    ) -> dict[str, Any]:
        """Run the supervisor audit graph; writes audit_trace.json under output_dir."""

        return audit_start(
            paper_url=paper_url,
            code_url=code_url,
            output_dir=output_dir,
            workspace=workspace,
            dataset=dataset,
            sandbox=sandbox,
            execution_mode=execution_mode,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            prepare_data=prepare_data,
            clone_repo=clone_repo,
        )

    @server.tool()
    def get_audit_status(trace_path: str | None = None, audit_id: str | None = None) -> dict[str, Any]:
        """Return high-level status from audit_trace.json."""

        return audit_get_status(trace_path=trace_path, audit_id=audit_id)

    @server.tool()
    def get_audit_trace(trace_path: str | None = None, audit_id: str | None = None) -> dict[str, Any]:
        """Return the full audit trace JSON."""

        return audit_get_trace(trace_path=trace_path, audit_id=audit_id)

    @server.tool()
    def get_audit_report(trace_path: str | None = None, audit_id: str | None = None) -> dict[str, Any]:
        """Load final report paths and content referenced by the audit trace."""

        return audit_get_report(trace_path=trace_path, audit_id=audit_id)

    @server.tool()
    def classify_failure(
        stdout: str = "",
        stderr: str = "",
        returncode: int | None = None,
        status: str | None = None,
        error: str | None = None,
        missing_files: list[str] | None = None,
        parser_error: str | None = None,
        verdict_reason: str | None = None,
    ) -> dict[str, Any]:
        """Classify a failed experiment run from logs."""

        return classify_failure_tool(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            status=status,
            error=error,
            missing_files=missing_files,
            parser_error=parser_error,
            verdict_reason=verdict_reason,
        )

    @server.tool()
    def propose_repair(classification: dict[str, Any]) -> dict[str, Any]:
        """Deterministic repair suggestion for a failure classification."""

        return propose_repair_tool(classification)

    return server


def run_mcp_server(manifest_root: Path = EXAMPLE_MANIFESTS_ROOT) -> None:
    """Run the ClaimBench MCP server over stdio."""

    create_mcp_server(manifest_root).run()


def _load_fastmcp() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise McpDependencyError(
            "The optional MCP dependency is not installed. Install it with: "
            "pip install -e '.[mcp]'"
        ) from exc
    return FastMCP
