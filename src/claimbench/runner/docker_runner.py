"""Docker-backed manifest experiment execution."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any

from claimbench.manifest import ClaimManifest
from claimbench.runner.executor import ExperimentRunResult, _find_experiment, _linked_claims
from claimbench.runner.metrics import MetricParseError, parse_metric
from claimbench.runner.verdict import compute_verdict

CONTAINER_WORKSPACE = PurePosixPath("/workspace")


def run_manifest_experiment_in_docker(
    manifest: ClaimManifest,
    experiment_id: str,
    *,
    workspace: Path,
    image: str = "python:3.10-slim",
    metric_output_path: Path | None = None,
    timeout_seconds: int = 300,
    network: str | None = "none",
    memory: str | None = "4g",
    cpus: str | None = "2",
) -> ExperimentRunResult:
    """Run a manifest experiment inside a Docker container."""

    experiment = _find_experiment(manifest, experiment_id)
    manifest_command = list(experiment["command"])
    host_workspace = workspace.resolve()
    container_workdir = _container_workdir(experiment.get("working_directory", "."))
    docker_command = build_docker_command(
        manifest_command,
        workspace=host_workspace,
        image=image,
        container_workdir=container_workdir,
        network=network,
        memory=memory,
        cpus=cpus,
    )

    started = time.monotonic()
    try:
        completed = subprocess.run(
            docker_command,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        runtime = time.monotonic() - started
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="timed_out",
            command=docker_command,
            returncode=None,
            runtime_seconds=runtime,
            stdout=_captured_text(exc.stdout),
            stderr=_captured_text(exc.stderr),
            observed_metric=None,
            verdicts=[],
            error=f"Docker run timed out after {timeout_seconds} seconds.",
        )
    except OSError as exc:
        runtime = time.monotonic() - started
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="failed",
            command=docker_command,
            returncode=None,
            runtime_seconds=runtime,
            stdout="",
            stderr="",
            observed_metric=None,
            verdicts=[],
            error=str(exc),
        )

    runtime = time.monotonic() - started
    if completed.returncode != 0:
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="failed",
            command=docker_command,
            returncode=completed.returncode,
            runtime_seconds=runtime,
            stdout=completed.stdout,
            stderr=completed.stderr,
            observed_metric=None,
            verdicts=[],
            error=f"Docker command exited with code {completed.returncode}.",
        )

    try:
        observed = parse_metric(
            experiment["metric_parser"],
            stdout=completed.stdout,
            output_path=_host_metric_path(host_workspace, metric_output_path),
        )
        verdicts = [
            compute_verdict(claim, observed)
            for claim in _linked_claims(manifest, experiment["linked_claim_ids"])
        ]
    except (MetricParseError, ValueError) as exc:
        return ExperimentRunResult(
            experiment_id=experiment_id,
            status="failed",
            command=docker_command,
            returncode=completed.returncode,
            runtime_seconds=runtime,
            stdout=completed.stdout,
            stderr=completed.stderr,
            observed_metric=None,
            verdicts=[],
            error=str(exc),
        )

    status = "succeeded"
    if any(verdict.status == "failed" for verdict in verdicts):
        status = "failed"
    elif any(verdict.status == "needs_review" for verdict in verdicts):
        status = "needs_review"

    return ExperimentRunResult(
        experiment_id=experiment_id,
        status=status,
        command=docker_command,
        returncode=completed.returncode,
        runtime_seconds=runtime,
        stdout=completed.stdout,
        stderr=completed.stderr,
        observed_metric=observed,
        verdicts=verdicts,
        error=None,
    )


def build_docker_command(
    manifest_command: list[str],
    *,
    workspace: Path,
    image: str,
    container_workdir: str,
    network: str | None,
    memory: str | None,
    cpus: str | None,
) -> list[str]:
    """Build the Docker CLI command for a manifest experiment."""

    command = [
        "docker",
        "run",
        "--rm",
        "--volume",
        f"{workspace}:/workspace",
        "--workdir",
        container_workdir,
    ]
    if network is not None:
        command.extend(["--network", network])
    if memory is not None:
        command.extend(["--memory", memory])
    if cpus is not None:
        command.extend(["--cpus", cpus])

    command.append(image)
    command.extend(manifest_command)
    return command


def _container_workdir(working_directory: str) -> str:
    path = PurePosixPath(working_directory)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Experiment working_directory must stay inside workspace: {working_directory}")
    return str(CONTAINER_WORKSPACE / path)


def _host_metric_path(workspace: Path, metric_output_path: Path | None) -> Path | None:
    if metric_output_path is None:
        return None
    if metric_output_path.is_absolute():
        return metric_output_path
    return workspace / metric_output_path


def _captured_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
