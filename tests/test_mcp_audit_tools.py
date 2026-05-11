from __future__ import annotations

from claimbench.tools.audit_mcp import classify_failure_tool, propose_repair_tool


def test_classify_failure_tool() -> None:
    payload = classify_failure_tool(status="timed_out")
    assert payload["failure_type"] == "timeout"


def test_propose_repair_tool() -> None:
    cls = classify_failure_tool(stderr="Could not find a version that satisfies", returncode=1)
    prop = propose_repair_tool(cls)
    assert prop["route_to"] == "environment_agent"
