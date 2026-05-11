# ClaimBench Multi-Agent Architecture

This document defines the target multi-agent architecture for ClaimBench. The current codebase contains the reproducibility engine: manifests, runners, reports, dashboard, and MCP-facing tools. The next layer should make this an agentic audit system that can inspect a new paper/repo, plan work, run sandboxed experiments, classify failures, repair safely, and report what was actually verified.

## Architecture Pattern

Use a **supervisor-orchestrated graph** rather than a fully free-form swarm.

The supervisor owns state, routing, retry budgets, safety policy, and final report assembly. Specialized agents work on bounded subtasks and return structured outputs. This keeps the system auditable while still showing real parallelism.

Recommended implementation stack:

- **LangGraph** for graph state, conditional routing, retries, and parallel branches.
- **Tool-calling/ReAct nodes** for repo inspection, failure repair, and claim/metric reasoning.
- **Existing ClaimBench tools** for deterministic actions: repo scan, manifest validation, sandbox run, metric parsing, report generation.
- **MCP server** as the external agent interface, not the internal orchestrator.

## High-Level Graph

```text
START
  |
  v
Supervisor: initialize audit state, safety policy, retry budgets
  |
  +--------------------+----------------------+----------------------+
  |                    |                      |                      |
  v                    v                      v                      v
Paper Agent       Repo Agent             Data Agent             Environment Agent
extract claims    scan repo/readme       detect datasets        infer dependencies
paper metadata    find entrypoints       prepare/download       build Docker plan
  |                    |                      |                      |
  +--------------------+----------------------+----------------------+
                           |
                           v
Supervisor: merge findings into draft ClaimManifest
                           |
                           v
Manifest Validator / Reviewer
                           |
                           v
Experiment Planner
                           |
                           v
Environment Builder  <-----------------------------+
                           |                        |
                           v                        |
Data Preparer        <------------------------+     |
                           |                  |     |
                           v                  |     |
Sandbox Executor     <------------------+     |     |
                           |            |     |     |
                           v            |     |     |
Metric Parser        <-------------+    |     |     |
                           |       |    |     |     |
                           v       |    |     |     |
Claim Comparator     |       |    |     |     |
                           |       |    |     |     |
            +--------------+       |    |     |     |
            |                      |    |     |     |
            v                      |    |     |     |
      Report Builder               |    |     |     |
            ^                      |    |     |     |
            |                      |    |     |     |
            +---- Failure Classifier ----+-----+-----+
                           |
                           v
                    Repair Decision
```

The repair loop is routed by failure type:

```text
dependency_version_conflict
  -> Environment Agent updates Dockerfile / lock plan
  -> Environment Builder rebuilds image
  -> Sandbox Executor retries

missing_dataset or missing_file
  -> Data Agent resolves/downloads/reformats data
  -> Data Preparer writes expected paths
  -> Sandbox Executor retries

command_failed from wrong command/path
  -> Repo Agent re-inspects README/scripts
  -> Experiment Planner adjusts command or working directory
  -> Sandbox Executor retries

metric_parse_failed or missing_metric_output
  -> Metric Parser Agent inspects stdout/files/artifacts
  -> Experiment Planner updates parser/output path
  -> Metric Parser retries, or Sandbox Executor retries if command args changed

timeout or out_of_memory
  -> Supervisor checks policy
  -> Environment Agent changes resources only if allowed
  -> Sandbox Executor retries, or report marks resource limit failure

claim_metric_mismatch
  -> no repair by default
  -> Reviewer/Report Builder records scientific mismatch
```

The supervisor stops the loop when:

- the run succeeds and metrics are parsed,
- the failure is not safely repairable,
- retry budget is exhausted,
- compute budget is exhausted,
- a human review gate is required.

## Agents

### Supervisor Agent

Responsibilities:

- Maintains audit state.
- Starts parallel branches.
- Enforces security policy and retry limits.
- Decides whether to run, retry, stop, or ask for review.
- Produces final status: `reproduced`, `partial`, `failed`, `needs_review`.

This should be deterministic where possible. The supervisor should not hallucinate paper claims or silently change commands.

### Paper Agent

Responsibilities:

- Fetch/read paper metadata.
- Extract candidate claims, metrics, tables, and paper locations.
- Assign confidence and evidence snippets.
- Mark uncertain claims as `unverified_candidate`.

Parallelizable with repo/data/environment inspection.

### Repo Agent

Responsibilities:

- Clone or inspect the code repository.
- Scan setup files, README commands, notebooks, scripts, examples, result files.
- Identify likely entrypoints and existing metric files.
- Return candidate commands with confidence.

Parallelizable with paper/data/environment inspection.

### Data Agent

Responsibilities:

- Identify datasets required by candidate experiments.
- Resolve download sources, expected layout, and checksums when possible.
- Prepare datasets in an audit workspace.
- Mark restricted, missing, or manual datasets explicitly.

Parallelizable with repo/paper/environment inspection.

### Environment Agent

Responsibilities:

- Infer dependencies from `requirements.txt`, `environment.yml`, `pyproject.toml`, README, and observed import errors.
- Generate a Dockerfile or environment plan.
- Build/pull images.
- Record image tag/digest and dependency decisions.

Parallelizable with paper/repo/data inspection before first run.

### Experiment Planner

Responsibilities:

- Links claims to commands and metric parsers.
- Selects the smallest credible experiment first.
- Produces a `ClaimManifest` or updates an existing draft.
- Refuses execution when required fields are unresolved.

### Sandbox Executor

Responsibilities:

- Runs reviewed experiments in Docker or another sandbox.
- Applies CPU, memory, timeout, disk, and network policy.
- Captures stdout, stderr, exit code, runtime, logs, artifacts.

This is a deterministic tool node, not an LLM node.

### Long-Run Executor

Responsibilities:

- Submits long CPU/GPU jobs to a remote worker, GPU server, Slurm cluster, Modal/E2B/RunPod, or self-hosted queue.
- Returns a `run_id` immediately instead of blocking the graph.
- Streams or periodically syncs logs, checkpoints, metrics, and resource usage.
- Supports resume/cancel when the backend allows it.
- Persists heartbeats so 24-hour jobs are not lost if the UI or local agent disconnects.

For long jobs, the graph should not keep an LLM call open. The graph should move into a durable state:

```text
queued -> provisioning -> building_env -> resolving_data -> running_remote
       -> checkpointing -> parsing_metrics -> comparing_claims -> report
```

The supervisor polls or receives events from the long-run backend. The agents only wake up when there is new evidence: logs, failure, checkpoint, metric file, or job completion.

### Metric Parser Agent

Responsibilities:

- Finds metrics in generated JSON/CSV/stdout/log files.
- Maps observed metrics to expected claim metrics.
- Reports parser uncertainty.

Start deterministic with manifest parsers; later add LLM assistance for locating metrics in unknown logs.

### Failure Classifier

Responsibilities:

- Classifies failures into structured categories:
  - `dependency_version_conflict`
  - `missing_dataset`
  - `missing_file`
  - `command_failed`
  - `metric_parse_failed`
  - `timeout`
  - `hardware_mismatch`
  - `network_blocked`
  - `manual_review_required`
- Extracts actionable details from stderr/stdout.

Example:

```json
{
  "failure_type": "dependency_version_conflict",
  "package": "numpy",
  "constraint": "<=2.1",
  "installed": "2.4",
  "suggested_fix": "pin numpy<2.2 in generated Dockerfile"
}
```

### Repair Agent

Responsibilities:

- Proposes safe fixes for classified failures.
- Applies only bounded, inspectable changes:
  - dependency pin change
  - Dockerfile update
  - dataset preparation step
  - metric output path correction
  - parser target correction
- Retries only within budget.
- Logs every repair attempt.

The repair agent should never silently rewrite scientific claims.

### Reviewer Agent

Responsibilities:

- Audits the evidence chain.
- Separates scientific failures from infrastructure failures.
- Produces human-readable limitations.
- Marks unresolved fields.

## What Can Run In Parallel

The first large parallel block after audit initialization:

```text
Paper Agent          -> claim candidates, expected metrics, paper locations
Repo Agent           -> setup files, commands, scripts, result files
Data Agent           -> dataset sources, access notes, local layout
Environment Agent    -> dependency plan, Dockerfile/image plan
```

These do not depend on each other and should be launched concurrently.

The second parallel block after repo scan:

```text
README command analysis
notebook/script analysis
existing result-file analysis
dependency-file analysis
```

The third parallel block after a failed run:

```text
Failure Classifier   -> classify stderr/stdout
Environment Agent    -> check dependency conflict
Data Agent           -> check missing dataset/file
Metric Parser Agent  -> check output/parser mismatch
```

The final report can also assemble sections in parallel:

```text
claim summary
environment summary
dataset provenance
run timeline
failure analysis
limitations
```

## Why Not Fully Decentralized Multi-Agent?

A free-for-all swarm is risky for this product because ClaimBench runs untrusted code and produces scientific claims. We need:

- deterministic state transitions,
- explicit provenance,
- bounded retries,
- inspectable repair attempts,
- security policy enforcement.

So the right pattern is **supervisor + specialized agents + deterministic tools**.

## Local vs Long GPU Runs

The architecture should support two execution classes.

### Local / Short Runs

Use this for demos and CPU-feasible papers:

- runtime: seconds to minutes,
- runs directly through `Sandbox Executor`,
- Docker container can be created and removed immediately,
- report is generated synchronously,
- best for ROCKET/MINIROCKET/LIBSVM/LIBLINEAR/small fastText-style tasks.

### Remote / Long GPU Runs

Use this for expensive papers:

- runtime: hours to days,
- submitted through `Long-Run Executor`,
- run state must be persisted outside the chat process,
- logs and metrics are streamed or polled,
- checkpoints and artifacts are stored in durable storage,
- report may be generated only after completion,
- partial reports should show progress and unresolved claims.

For a 24-hour GPU reproduction, ClaimBench should not behave like a normal CLI command waiting for output. It should behave like an experiment tracking system:

```text
agent prepares manifest
  -> environment image built/pushed
  -> dataset staged
  -> job submitted to GPU server
  -> run_id returned
  -> dashboard polls status
  -> logs/checkpoints synced
  -> metrics parsed at completion
  -> report generated
```

This is feasible if we have a GPU server, but the scope changes. The hard requirements become:

- remote job queue,
- artifact store,
- checkpoint/log syncing,
- budget controls,
- durable run database,
- restart/resume handling,
- clear distinction between "training still running" and "claim not reproduced".

The first product milestone should still prove short local runs. The long-GPU architecture should be added as a second executor backend, not mixed into the local MVP.

## State Model

Suggested LangGraph state:

```python
class AuditState(TypedDict):
    paper_url: str
    code_url: str
    output_dir: str
    repo_dir: str | None
    manifest_path: str | None
    paper_claims: list[dict]
    repo_scan: dict | None
    dataset_plan: dict | None
    environment_plan: dict | None
    experiments: list[dict]
    attempts: list[dict]
    current_error: dict | None
    repair_history: list[dict]
    artifacts: list[dict]
    final_report_path: str | None
    status: str
```

## Implementation Phases

### Phase 1: Deterministic Graph

- Add `claimbench.agents.audit_graph`.
- Implement graph nodes without LLM first.
- Nodes call existing functions:
  - `scan_repository`
  - `prepare_audit_manifest` (dispatches via `claimbench.audit.registry` to `claimbench.recipes.*`)
  - `prepare_ucr_dataset` (`claimbench.recipes.ucr_archive`, re-exported from `claimbench.audit`)
  - `run_paper`
  - report generation
- Add run trace JSON so the user can see the graph path.

### Phase 2: Failure Classifier + Repair Loop

- Add structured failure classification from stdout/stderr.
- Add repair suggestions for dependency conflicts, missing datasets, and parser failures.
- Retry with strict budget.
- Persist `repair_history`.

### Phase 3: LLM/ReAct Nodes

- Add LLM-backed claim extraction.
- Add LLM-backed README command interpretation.
- Add LLM-backed repair proposal, but keep application of fixes deterministic and reviewed.

### Phase 4: MCP Tools

Expose graph actions through MCP:

- `start_audit`
- `get_audit_status`
- `get_audit_trace`
- `get_audit_report`
- `classify_failure`
- `propose_repair`

## Demo Story

The demo should visibly show that this is not a sequential script:

1. User enters paper URL and GitHub URL.
2. UI shows parallel branches:
   - Paper Agent reading claims.
   - Repo Agent scanning code.
   - Data Agent resolving datasets.
   - Environment Agent building Docker plan.
3. Supervisor merges results into a manifest.
4. Executor runs in Docker.
5. If it fails, Failure Classifier and Repair Agent activate.
6. UI shows retry trace.
7. Final report explains what reproduced and what did not.

This is the product experience that justifies the MCP/AI/multi-agent framing.
