from __future__ import annotations

from typing import Any, Callable

import pytest

from claimbench import mcp_server
from claimbench.mcp_server import McpDependencyError, create_mcp_server


class FakeFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tools: dict[str, Callable[..., dict[str, Any]]] = {}
        self.ran = False

    def tool(self) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
        def decorator(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
            self.tools[func.__name__] = func
            return func

        return decorator

    def run(self) -> None:
        self.ran = True


def test_create_mcp_server_registers_read_only_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_load_fastmcp", lambda: FakeFastMCP)

    server = create_mcp_server()

    assert server.name == "claimbench"
    assert set(server.tools) == {
        "cached_report",
        "claim_evidence",
        "list_papers",
        "validate_manifest",
        "start_audit",
        "get_audit_status",
        "get_audit_trace",
        "get_audit_report",
        "classify_failure",
        "propose_repair",
    }
    assert server.tools["list_papers"]()["papers"][0]["paper_id"] == "minirocket_2012_08791"
    evidence = server.tools["claim_evidence"](
        "quant_2308_00928",
        "quant_claim_minimal_features",
    )
    assert evidence["evidence"]["observed_metric"] == "1.0"
    report = server.tools["cached_report"](paper_id="quant_2308_00928")
    assert report["report"]["summary"]["failure_category_counts"] == {"none": 1}
    assert report["report"]["experiments"][0]["failure_category"] == "none"


def test_run_mcp_server_delegates_to_fastmcp(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeFastMCP] = []

    def fake_fastmcp(name: str) -> FakeFastMCP:
        server = FakeFastMCP(name)
        created.append(server)
        return server

    monkeypatch.setattr(mcp_server, "_load_fastmcp", lambda: fake_fastmcp)

    mcp_server.run_mcp_server()

    assert created
    assert created[0].ran is True


def test_create_mcp_server_surfaces_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_missing_dependency() -> None:
        raise McpDependencyError("Install it with: pip install -e '.[mcp]'")

    monkeypatch.setattr(mcp_server, "_load_fastmcp", raise_missing_dependency)

    with pytest.raises(McpDependencyError, match=r"\.\[mcp\]"):
        create_mcp_server()
