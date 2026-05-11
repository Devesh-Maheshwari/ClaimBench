"""Audit graph helpers for CLI and MCP (minimal shared surface)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from claimbench.agents.audit_graph import audit_state_to_jsonable, run_agent_audit
from claimbench.agents.failure_classifier import classify_failure, classification_to_dict, propose_repair

_AUDIT_REGISTRY: dict[str, Path] = {}


def start_audit(
    *,
    paper_url: str,
    code_url: str,
    output_dir: str,
    workspace: str | None = None,
    dataset: str = "Coffee",
    num_kernels: int = 1000,
    code_commit: str | None = None,
    sandbox: str = "docker",
    execution_mode: str = "cpu",
    max_retries: int = 3,
    timeout_seconds: int = 300,
    docker_image: str | None = None,
    docker_network: str = "none",
    docker_memory: str = "4g",
    docker_cpus: str = "2",
    prepare_data: bool = True,
    clone_repo: bool = True,
) -> dict[str, Any]:
    """Run the deterministic audit graph and register the trace path."""

    out = Path(output_dir)
    ws = Path(workspace) if workspace else out
    audit_id = str(uuid.uuid4())
    backend = "remote_gpu" if execution_mode == "gpu" else "local_docker"
    state = run_agent_audit(
        paper_url=paper_url,
        code_url=code_url,
        output_dir=out,
        workspace=ws,
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
        trace_path=out / "audit_trace.json",
    )
    trace_path = out / "audit_trace.json"
    _AUDIT_REGISTRY[audit_id] = trace_path
    payload = audit_state_to_jsonable(state)
    payload["audit_id"] = audit_id
    payload["trace_path"] = str(trace_path)
    return payload


def get_audit_status(*, trace_path: str | None = None, audit_id: str | None = None) -> dict[str, Any]:
    path = _resolve_trace_path(trace_path=trace_path, audit_id=audit_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "trace_path": str(path),
        "status": data.get("status"),
        "retry_count": data.get("retry_count", 0),
        "execution_backend": data.get("execution_backend"),
    }


def get_audit_trace(*, trace_path: str | None = None, audit_id: str | None = None) -> dict[str, Any]:
    path = _resolve_trace_path(trace_path=trace_path, audit_id=audit_id)
    return json.loads(path.read_text(encoding="utf-8"))


def get_audit_report(*, trace_path: str | None = None, audit_id: str | None = None) -> dict[str, Any]:
    trace = get_audit_trace(trace_path=trace_path, audit_id=audit_id)
    md_path = trace.get("final_report_path")
    json_path = trace.get("final_report_json_path")
    out: dict[str, Any] = {"markdown_path": md_path, "json_path": json_path}
    if md_path and Path(md_path).exists():
        out["markdown"] = Path(md_path).read_text(encoding="utf-8")
    if json_path and Path(json_path).exists():
        out["report"] = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return out


def classify_failure_tool(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int | None = None,
    status: str | None = None,
    error: str | None = None,
    missing_files: list[str] | None = None,
    parser_error: str | None = None,
    verdict_reason: str | None = None,
) -> dict[str, Any]:
    fc = classify_failure(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        status=status,
        error=error,
        missing_files=missing_files,
        parser_error=parser_error,
        verdict_reason=verdict_reason,
    )
    return classification_to_dict(fc)


def propose_repair_tool(classification: dict[str, Any]) -> dict[str, Any]:
    from claimbench.agents.failure_classifier import FailureClassification

    fc = FailureClassification(
        failure_type=classification["failure_type"],  # type: ignore[arg-type]
        evidence=dict(classification.get("evidence") or {}),
        suggested_fix=str(classification["suggested_fix"]),
        retryable=bool(classification["retryable"]),
        route_to=classification["route_to"],  # type: ignore[arg-type]
    )
    return propose_repair(fc)


def _resolve_trace_path(*, trace_path: str | None, audit_id: str | None) -> Path:
    if trace_path:
        return Path(trace_path)
    if audit_id and audit_id in _AUDIT_REGISTRY:
        return _AUDIT_REGISTRY[audit_id]
    raise ValueError("Provide trace_path or a valid audit_id from start_audit.")
