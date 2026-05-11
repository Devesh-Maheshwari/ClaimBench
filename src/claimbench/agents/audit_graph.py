"""LangGraph-style deterministic audit pipeline (supervisor orchestration, no LLM)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict

from claimbench.agents.failure_classifier import (
    FailureClassification,
    classify_failure,
    classification_to_dict,
    propose_repair,
)
from claimbench.audit import prepare_audit_manifest, prepare_ucr_dataset
from claimbench.manifest import ClaimManifest, load_manifest
from claimbench.report import generate_reproducibility_report, report_to_dict, report_to_markdown
from claimbench.runner.artifacts import write_run_artifacts
from claimbench.runner.backends import (
    ExecutionContext,
    LocalDockerExecutor,
    RemoteGpuExecutor,
    RemoteRunHandle,
)


class AuditState(TypedDict, total=False):
    """Supervisor-owned audit state persisted into audit_trace.json."""

    paper_url: str
    code_url: str
    output_dir: str
    dataset: str
    num_kernels: int
    code_commit: str | None
    sandbox: str
    execution_backend: str
    max_retries: int
    retry_count: int
    repo_dir: str | None
    manifest_path: str | None
    scan_path: str | None
    paper_claims: list[dict[str, Any]]
    repo_scan: dict[str, Any] | None
    dataset_plan: dict[str, Any] | None
    environment_plan: dict[str, Any] | None
    experiments: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    current_classification: dict[str, Any] | None
    repair_history: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    branch_traces: dict[str, Any]
    graph_trace: list[dict[str, Any]]
    final_report_path: str | None
    final_report_json_path: str | None
    run_summary_path: str | None
    status: str
    remote_run_handles: list[dict[str, Any]]
    error: str | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _initial_state(
    *,
    paper_url: str,
    code_url: str,
    output_dir: Path,
    dataset: str,
    num_kernels: int,
    code_commit: str | None,
    sandbox: str,
    execution_backend: str,
    max_retries: int,
) -> AuditState:
    return AuditState(
        paper_url=paper_url,
        code_url=code_url,
        output_dir=str(output_dir.resolve()),
        dataset=dataset,
        num_kernels=num_kernels,
        code_commit=code_commit,
        sandbox=sandbox,
        execution_backend=execution_backend,
        max_retries=max_retries,
        retry_count=0,
        repo_dir=None,
        manifest_path=None,
        scan_path=None,
        paper_claims=[],
        repo_scan=None,
        dataset_plan=None,
        environment_plan=None,
        experiments=[],
        attempts=[],
        current_classification=None,
        repair_history=[],
        artifacts=[],
        branch_traces={},
        graph_trace=[],
        final_report_path=None,
        final_report_json_path=None,
        run_summary_path=None,
        status="initialized",
        remote_run_handles=[],
        error=None,
    )


def node_initialize(state: AuditState) -> None:
    _append_trace(state, "initialize", {"output_dir": state["output_dir"]})
    state["status"] = "inspect_parallel"


def node_parallel_prep(
    state: AuditState,
    *,
    clone_repo: bool,
    prepare_data: bool,
) -> None:
    """Run dataset prep and manifest/repo prep concurrently where possible."""

    output_dir = Path(state["output_dir"])
    _append_trace(state, "parallel_prep_start", {})

    def do_manifest() -> dict[str, Any]:
        return prepare_audit_manifest(
            paper_url=state["paper_url"],
            code_url=state["code_url"],
            output_dir=output_dir,
            dataset=state["dataset"],
            num_kernels=state["num_kernels"],
            code_commit=state.get("code_commit"),
            clone_repo=clone_repo,
        )

    def do_data() -> dict[str, Any]:
        if not prepare_data:
            return {"status": "skipped"}
        return prepare_ucr_dataset(output_dir=output_dir, dataset=state["dataset"])

    prepared: dict[str, Any] | None = None
    data_summary: dict[str, Any] | None = None
    errors: list[str] = []

    if prepare_data:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_manifest = pool.submit(do_manifest)
            fut_data = pool.submit(do_data)
            try:
                prepared = fut_manifest.result()
            except Exception as exc:  # noqa: BLE001 - surfaced in trace
                errors.append(f"manifest_prep: {exc}")
            try:
                data_summary = fut_data.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"data_prep: {exc}")
    else:
        try:
            prepared = do_manifest()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"manifest_prep: {exc}")
        data_summary = {"status": "skipped"}

    if errors:
        state["error"] = "; ".join(errors)
        state["status"] = "failed"
        _append_trace(state, "parallel_prep_error", {"errors": errors})
        return

    assert prepared is not None
    manifest_path: Path = prepared["manifest_path"]
    state["manifest_path"] = str(manifest_path)
    state["repo_dir"] = str(prepared["repo_dir"])
    if prepared.get("scan_path"):
        state["scan_path"] = str(prepared["scan_path"])

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    state["paper_claims"] = list(manifest.get("claims", []))
    state["environment_plan"] = dict(manifest.get("environment", {}))
    state["experiments"] = list(manifest.get("experiments", []))

    if data_summary is not None:
        state["dataset_plan"] = data_summary

    _append_trace(
        state,
        "parallel_prep_done",
        {"manifest_path": state["manifest_path"], "data": data_summary},
    )


def node_parallel_inspect(state: AuditState) -> None:
    """Record parallel Paper / Repo / Data / Environment agent branches (deterministic reads)."""

    if state.get("status") == "failed":
        return
    manifest_path = Path(state["manifest_path"] or "")
    scan_path = Path(state["scan_path"]) if state.get("scan_path") else None
    out = Path(state["output_dir"])

    def paper_branch() -> dict[str, Any]:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "agent": "paper",
            "claims_count": len(data.get("claims", [])),
            "paper_id": data.get("paper", {}).get("paper_id"),
        }

    def repo_branch() -> dict[str, Any]:
        if scan_path is None or not scan_path.exists():
            return {"agent": "repo", "scan_loaded": False}
        raw = json.loads(scan_path.read_text(encoding="utf-8"))
        keys = list(raw.keys()) if isinstance(raw, dict) else []
        return {"agent": "repo", "scan_loaded": True, "top_level_keys": keys}

    def data_branch() -> dict[str, Any]:
        return {"agent": "data", "summary": state.get("dataset_plan")}

    def env_branch() -> dict[str, Any]:
        return {"agent": "environment", "plan": state.get("environment_plan")}

    branches: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_p = pool.submit(paper_branch)
        f_r = pool.submit(repo_branch)
        f_d = pool.submit(data_branch)
        f_e = pool.submit(env_branch)
        branches["paper"] = f_p.result()
        branches["repo"] = f_r.result()
        branches["data"] = f_d.result()
        branches["environment"] = f_e.result()

    state["branch_traces"] = branches
    if scan_path and scan_path.exists():
        state["repo_scan"] = json.loads(scan_path.read_text(encoding="utf-8"))
    _append_trace(state, "parallel_inspect", {"branches": branches})
    state["status"] = "merge_manifest"


def node_merge_manifest(state: AuditState) -> None:
    if state.get("status") == "failed":
        return
    _append_trace(
        state,
        "merge_manifest",
        {
            "manifest_path": state["manifest_path"],
            "experiments": len(state.get("experiments") or []),
        },
    )
    state["status"] = "execute"


def node_execute_and_maybe_repair(
    state: AuditState,
    *,
    workspace: Path,
    timeout_seconds: int,
    docker_image: str | None,
    docker_network: str,
    docker_memory: str,
    docker_cpus: str,
    prepare_data: bool,
) -> None:
    """Run executor; on failure classify, log repair, retry within budget (no claim mutation)."""

    if state.get("status") == "failed":
        return
    output_dir = Path(state["output_dir"])
    manifest_path = Path(state["manifest_path"] or "")
    ctx = ExecutionContext(
        workspace=workspace,
        timeout_seconds=timeout_seconds,
        docker_image=docker_image,
        docker_network=docker_network,
        docker_memory=docker_memory,
        docker_cpus=docker_cpus,
    )

    if state["execution_backend"] == "remote_gpu":
        backend = RemoteGpuExecutor()
    else:
        sandbox_lit: Literal["local", "docker"] = (
            "docker" if state["sandbox"] == "docker" else "local"
        )
        backend = LocalDockerExecutor(sandbox=sandbox_lit)

    manifest = load_manifest(manifest_path)
    max_retries = int(state.get("max_retries") or 0)
    retry_count = 0

    while True:
        attempt_entry: dict[str, Any] = {
            "retry_count": retry_count,
            "ts": _utc_now_iso(),
            "results": [],
        }
        results_any: list[Any] = []
        stopped_gpu = False

        missing_before = _missing_data_files(output_dir, state["dataset"]) if prepare_data else []
        if missing_before:
            fc = classify_failure(missing_files=missing_before, status="failed")
            state["current_classification"] = classification_to_dict(fc)
            attempt_entry["preflight_failure"] = classification_to_dict(fc)
            state["attempts"].append(attempt_entry)
            _append_trace(state, "classify_failure", {"classification": state["current_classification"]})
            if fc.retryable and retry_count < max_retries:
                state["repair_history"].append(
                    {"retry": retry_count, "repair": propose_repair(fc), "note": "retry_after_preflight"}
                )
                _apply_deterministic_repair(state, fc, prepare_data=prepare_data)
                retry_count += 1
                state["retry_count"] = retry_count
                _append_trace(state, "repair_route", {"to": fc.route_to, "retry": retry_count})
                continue
            state["status"] = "failed"
            _append_trace(state, "execute_stopped", {"reason": "preflight_missing_data"})
            return

        for experiment in manifest.data.get("experiments", []):
            experiment_id = experiment["experiment_id"]
            metric_output = _infer_metric_output_path(workspace, experiment)
            raw = backend.run_experiment(
                manifest,
                experiment_id,
                metric_output_path=metric_output,
                ctx=ctx,
            )
            if isinstance(raw, RemoteRunHandle):
                attempt_entry["results"].append(
                    {
                        "experiment_id": experiment_id,
                        "remote": {"run_id": raw.run_id, "status": raw.status, "message": raw.message},
                    }
                )
                state["remote_run_handles"].append(
                    {"experiment_id": experiment_id, "run_id": raw.run_id, "status": raw.status}
                )
                stopped_gpu = True
                continue
            result = raw
            artifact_summary = write_run_artifacts(
                manifest,
                result,
                output_dir / "run" / "experiments" / experiment_id,
                metric_output_path=metric_output,
            )
            state["artifacts"].append(artifact_summary)
            attempt_entry["results"].append(
                {
                    "experiment_id": experiment_id,
                    "status": result.status,
                    "returncode": result.returncode,
                    "error": result.error,
                }
            )
            results_any.append(result)

        state["attempts"].append(attempt_entry)
        _append_trace(state, "executor", {"attempt": attempt_entry})

        if stopped_gpu:
            state["status"] = "submitted_remote"
            _append_trace(state, "executor_gpu_stub", {"handles": state["remote_run_handles"]})
            return

        # Local/docker: evaluate outcomes
        bad = next((r for r in results_any if r.status in {"failed", "timed_out"}), None)
        needs_review_only = all(r.status in {"succeeded", "needs_review"} for r in results_any) and any(
            r.status == "needs_review" for r in results_any
        )
        if bad is None and results_any:
            if needs_review_only:
                state["status"] = "needs_review"
            else:
                state["status"] = "succeeded"
            return

        if not results_any:
            state["status"] = "failed"
            return

        verdict_reason = None
        for r in results_any:
            for v in r.verdicts:
                if v.status == "failed":
                    verdict_reason = v.reason
                    break
            if verdict_reason:
                break

        fc = classify_failure(
            stdout=bad.stdout if bad else "",
            stderr=bad.stderr if bad else "",
            returncode=bad.returncode if bad else None,
            status=bad.status if bad else None,
            error=bad.error if bad else None,
            parser_error=bad.error if bad and bad.error and "metric" in bad.error.lower() else None,
            verdict_reason=verdict_reason,
        )
        state["current_classification"] = classification_to_dict(fc)
        _append_trace(state, "classify_failure", {"classification": state["current_classification"]})

        if fc.failure_type == "claim_metric_mismatch":
            state["repair_history"].append(
                {"retry": retry_count, "skipped_repair": True, "reason": "claim_metric_mismatch_policy"}
            )
            state["status"] = "failed"
            return

        if fc.retryable and retry_count < max_retries:
            repair = propose_repair(fc)
            state["repair_history"].append({"retry": retry_count, "repair": repair})
            _apply_deterministic_repair(state, fc, prepare_data=prepare_data)
            retry_count += 1
            state["retry_count"] = retry_count
            _append_trace(state, "repair_route", {"to": fc.route_to, "retry": retry_count})
            continue

        state["status"] = "failed"
        return


def _append_trace(state: AuditState, phase: str, detail: dict[str, Any] | None = None) -> None:
    entry: dict[str, Any] = {"ts": _utc_now_iso(), "phase": phase}
    if detail:
        entry["detail"] = detail
    state.setdefault("graph_trace", []).append(entry)


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


def _apply_deterministic_repair(
    state: AuditState,
    fc: FailureClassification,
    *,
    prepare_data: bool,
) -> None:
    """Bounded, non-claim-changing fixes before a retry (MVP: data prep only)."""

    out = Path(state["output_dir"])
    if not prepare_data:
        return
    if fc.failure_type in {"missing_dataset", "missing_file"} and fc.route_to == "data_agent":
        try:
            summary = prepare_ucr_dataset(output_dir=out, dataset=state["dataset"])
            state["dataset_plan"] = summary
            _append_trace(state, "repair_apply", {"action": "prepare_ucr_dataset", "summary_status": summary.get("status")})
        except Exception as exc:  # noqa: BLE001
            _append_trace(state, "repair_apply_failed", {"action": "prepare_ucr_dataset", "error": str(exc)})


def _missing_data_files(output_dir: Path, dataset: str) -> list[str]:
    train = output_dir / "data" / "UCR" / dataset / f"{dataset}_TRAIN.tsv"
    test = output_dir / "data" / "UCR" / dataset / f"{dataset}_TEST.tsv"
    missing = []
    if not train.exists():
        missing.append(str(train))
    if not test.exists():
        missing.append(str(test))
    return missing


def node_final_report(state: AuditState, *, workspace: Path) -> None:
    if not state.get("manifest_path"):
        return
    if state.get("status") == "submitted_remote":
        _append_trace(state, "final_report_skipped", {"reason": "remote_gpu_async"})
        return

    manifest_path = Path(state["manifest_path"] or "")
    if not manifest_path.exists():
        return
    manifest = load_manifest(manifest_path)
    output_dir = Path(state["output_dir"]) / "run"
    output_dir.mkdir(parents=True, exist_ok=True)

    from claimbench.runner.executor import ExperimentRunResult
    from claimbench.runner.verdict import ClaimVerdict

    run_results: list[ExperimentRunResult] = []
    for experiment in manifest.data.get("experiments", []):
        exp_dir = output_dir / "experiments" / experiment["experiment_id"]
        result_path = exp_dir / "result.json"
        if not result_path.exists():
            continue
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        verdicts_raw = payload.get("verdicts") or []
        verdicts = [ClaimVerdict(**v) for v in verdicts_raw if isinstance(v, dict)]
        run_results.append(
            ExperimentRunResult(
                experiment_id=payload["experiment_id"],
                status=payload["status"],
                command=list(payload["command"]),
                returncode=payload.get("returncode"),
                runtime_seconds=float(payload.get("runtime_seconds", 0.0)),
                stdout=payload.get("stdout", ""),
                stderr=payload.get("stderr", ""),
                observed_metric=payload.get("observed_metric"),
                verdicts=verdicts,
                error=payload.get("error"),
            )
        )

    report = generate_reproducibility_report(manifest, run_results)

    report_json_path = output_dir / "report.json"
    report_md_path = output_dir / "report.md"
    summary_path = output_dir / "run_summary.json"
    report_json_path.write_text(
        json.dumps(report_to_dict(report), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    report_md_path.write_text(report_to_markdown(report) + "\n", encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "paper_id": manifest.paper_id,
                "manifest_path": str(manifest_path),
                "sandbox": state["sandbox"],
                "execution_backend": state["execution_backend"],
                "overall_status": report.summary["overall_status"],
                "audit_status": state["status"],
                "retry_count": state.get("retry_count", 0),
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    state["final_report_json_path"] = str(report_json_path)
    state["final_report_path"] = str(report_md_path)
    state["run_summary_path"] = str(summary_path)
    _append_trace(
        state,
        "final_report",
        {"report_json": str(report_json_path), "report_md": str(report_md_path)},
    )


def run_agent_audit(
    *,
    paper_url: str,
    code_url: str,
    output_dir: Path,
    workspace: Path,
    dataset: str = "Coffee",
    num_kernels: int = 1000,
    code_commit: str | None = None,
    sandbox: str = "docker",
    execution_backend: Literal["local_docker", "remote_gpu"] = "local_docker",
    max_retries: int = 3,
    timeout_seconds: int = 300,
    docker_image: str | None = None,
    docker_network: str = "none",
    docker_memory: str = "4g",
    docker_cpus: str = "2",
    prepare_data: bool = True,
    clone_repo: bool = True,
    trace_path: Path | None = None,
) -> AuditState:
    """Drive the full deterministic graph and optionally persist ``audit_trace.json``."""

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state = _initial_state(
        paper_url=paper_url,
        code_url=code_url,
        output_dir=output_dir,
        dataset=dataset,
        num_kernels=num_kernels,
        code_commit=code_commit,
        sandbox=sandbox,
        execution_backend=execution_backend,
        max_retries=max_retries,
    )

    node_initialize(state)
    node_parallel_prep(state, clone_repo=clone_repo, prepare_data=prepare_data)
    node_parallel_inspect(state)
    node_merge_manifest(state)
    node_execute_and_maybe_repair(
        state,
        workspace=workspace,
        timeout_seconds=timeout_seconds,
        docker_image=docker_image,
        docker_network=docker_network,
        docker_memory=docker_memory,
        docker_cpus=docker_cpus,
        prepare_data=prepare_data,
    )
    node_final_report(state, workspace=workspace)

    dest = trace_path or (output_dir / "audit_trace.json")
    dest.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")
    return state


def audit_state_to_jsonable(state: AuditState) -> dict[str, Any]:
    return json.loads(json.dumps(state, default=str))
