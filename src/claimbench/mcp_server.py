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
