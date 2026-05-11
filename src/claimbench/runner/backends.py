"""Execution backends for manifest experiments (local/Docker CPU and remote GPU stub)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from claimbench.manifest import ClaimManifest
from claimbench.runner.docker_runner import run_manifest_experiment_in_docker
from claimbench.runner.executor import ExperimentRunResult, run_manifest_experiment

RunLifecycleState = Literal[
    "queued",
    "preparing",
    "building_env",
    "resolving_data",
    "running",
    "parsing_metrics",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
]


@dataclass(frozen=True)
class RemoteRunHandle:
    """Non-blocking handle for a submitted remote GPU job (stub)."""

    run_id: str
    status: RunLifecycleState
    message: str | None = None


@dataclass(frozen=True)
class ExecutionContext:
    """Parameters shared across backend executions."""

    workspace: Path
    timeout_seconds: int
    docker_image: str | None = None
    docker_network: str = "none"
    docker_memory: str = "4g"
    docker_cpus: str = "2"


class ExperimentExecutionBackend(Protocol):
    """Runs manifest experiments either synchronously or as remote submissions."""

    name: str

    def run_experiment(
        self,
        manifest: ClaimManifest,
        experiment_id: str,
        *,
        metric_output_path: Path | None,
        ctx: ExecutionContext,
    ) -> ExperimentRunResult | RemoteRunHandle:
        ...


@dataclass
class LocalDockerExecutor:
    """CPU execution through the existing local or Docker runners."""

    sandbox: Literal["local", "docker"]
    name: str = "local_docker"

    def run_experiment(
        self,
        manifest: ClaimManifest,
        experiment_id: str,
        *,
        metric_output_path: Path | None,
        ctx: ExecutionContext,
    ) -> ExperimentRunResult:
        if self.sandbox == "local":
            return run_manifest_experiment(
                manifest,
                experiment_id,
                workspace=ctx.workspace,
                metric_output_path=metric_output_path,
                timeout_seconds=ctx.timeout_seconds,
            )
        image = ctx.docker_image or manifest.data["environment"]["base_image"]
        return run_manifest_experiment_in_docker(
            manifest,
            experiment_id,
            workspace=ctx.workspace,
            image=image,
            metric_output_path=metric_output_path,
            timeout_seconds=ctx.timeout_seconds,
            network=ctx.docker_network,
            memory=ctx.docker_memory,
            cpus=ctx.docker_cpus,
        )


@dataclass
class RemoteGpuExecutor:
    """Stub remote GPU executor: returns immediately with a queued run_id."""

    name: str = "remote_gpu"

    def run_experiment(
        self,
        manifest: ClaimManifest,
        experiment_id: str,
        *,
        metric_output_path: Path | None,
        ctx: ExecutionContext,
    ) -> RemoteRunHandle:
        _ = (metric_output_path, ctx)  # Reserved for a real backend.
        rid = f"gpu-stub-{uuid.uuid4().hex[:8]}"
        return RemoteRunHandle(
            run_id=rid,
            status="queued",
            message=f"Stub submission for {manifest.paper_id}:{experiment_id}",
        )


def poll_remote_stub(handle: RemoteRunHandle) -> RemoteRunHandle:
    """No-op poll helper for the stub (remains queued until a real worker exists)."""

    return handle
