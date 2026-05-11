from __future__ import annotations

import json
from pathlib import Path

from claimbench.dashboard.app import load_audit_trace_file


def test_load_audit_trace_file(tmp_path: Path) -> None:
    trace = {
        "status": "succeeded",
        "branch_traces": {"paper": {"agent": "paper"}},
        "graph_trace": [{"ts": "t", "phase": "initialize"}],
        "repair_history": [],
    }
    p = tmp_path / "audit_trace.json"
    p.write_text(json.dumps(trace), encoding="utf-8")
    branches, timeline, retries, raw = load_audit_trace_file(str(p))
    assert "Paper Agent" in branches
    assert "initialize" in timeline
    assert "No repairs" in retries or "_No repairs" in retries
    assert "succeeded" in raw


def test_load_audit_trace_missing_file(tmp_path: Path) -> None:
    branches, _, _, raw = load_audit_trace_file(str(tmp_path / "nope.json"))
    assert "not found" in branches.lower()
    assert raw == ""
