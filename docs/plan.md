# ClaimBench - Portfolio-Grade 10-Week Build Plan

> Graduate portfolio project plan. Built to be referenced during implementation.
> Status: draft v3 (2026-05-03)

---

## 1. Final Product Vision

The final product is a hosted Hugging Face Space called:

> **ClaimBench: Reproducibility Auditor for ML Papers**

The demo should feel like **Papers with Code plus a reproducibility audit layer**. A recruiter opens the Space, selects a curated ML paper, clicks a claim, and sees whether the paper's reported result was actually reproduced from code.

This is not primarily a "paper to MCP server" project anymore. Paper2Agent already covers that broad direction. This project is differentiated as:

> **A claim-level trust and verification system for ML papers and paper agents.**

Paper2Agent asks: "Can we turn papers into agents?"

ClaimBench asks: "Can we verify whether the agent/repo actually reproduces the paper's claims, and can we explain failures precisely?"

### What the recruiter sees in the live demo

The Hugging Face Space should show a simple dashboard:

1. **Pick a paper** from curated examples.
2. **View extracted claims** from tables/sections in the paper.
3. **Click Verify Claim** to replay or run the linked experiment.
4. **See expected vs. observed metrics** with tolerance and verdict.
5. **Inspect evidence**: command, environment, dataset, logs, metric parser output, artifacts.
6. **Generate a reproducibility report** summarizing what reproduced, what failed, and why.
7. Optionally **ask an agent** questions like "Why did this claim fail?" or "Which claim has weakest evidence?"

Public demo mode should use cached/precomputed runs for speed, with one optional lightweight live run for credibility.

The 3 gold-set papers are not the product. They are the acceptance test suite and public demo corpus. The product must include a reusable onboarding flow for a new paper:

```text
arxiv_id + github_url + optional commit
  -> fetch paper metadata
  -> scan repository
  -> propose candidate claims
  -> propose executable experiments
  -> generate draft ClaimManifest
  -> validate manifest
  -> run sandboxed verification
  -> produce reproducibility report
```

For safety and cost, the hosted public demo should not execute arbitrary user-submitted repositories. But the local/self-hosted version must let a technical user add a new paper and see where the process succeeds or fails.

### Core positioning

The project should be described as:

> I built a claim-level reproducibility auditor for ML papers: it turns selected papers with code into executable manifests, runs sandboxed experiments, verifies reported claims, and produces failure-aware reproducibility reports through a web dashboard and MCP tools.

### Hiring signal

This project should signal:

- **ML systems engineering**: environment capture, datasets, metrics, experiments, reproducibility.
- **Production maturity**: sandboxing, async jobs, logs, artifacts, state machines, quotas, cached public demo.
- **Research judgment**: clear failure taxonomy and honest limitations.
- **Product sense**: a non-technical recruiter can understand the demo in 60 seconds.
- **Agent infrastructure awareness**: MCP is used where it adds value, but the product is not hidden behind MCP setup.

### Non-goals

- Do not claim to reproduce arbitrary papers end-to-end automatically.
- Do not allow public users to run arbitrary GitHub repos on hosted infrastructure.
- Do not build a chatbot-only demo.
- Do not overfocus on UI before the reproducibility backend is credible.
- Do not compete with Paper2Agent on general "paper to agent" conversion.

---

## 2. Product Requirements

### Demo requirements

The Hugging Face Space must support this 60-second flow:

1. User selects a paper.
2. Dashboard loads paper metadata, repo commit, dataset, hardware profile, and reproducibility score.
3. User sees a claim table with expected metrics, observed metrics, verdicts, and failure categories.
4. User clicks a claim to open the evidence panel.
5. User clicks `Verify Claim`.
6. Public demo replays a cached run immediately; optional lightweight live mode can run one small experiment.
7. User opens a generated reproducibility report.

### Public dashboard components

- **Paper selector**: curated papers only.
- **Summary card**: title, arXiv URL, repo URL, commit SHA, dataset, hardware, overall verdict.
- **Claims table**: claim text, paper source, expected metric, observed metric, tolerance, status.
- **Verification panel**: run timeline, command, environment, dataset version, logs, parser output.
- **Report tab**: markdown or HTML reproducibility report.
- **Agent Q&A tab**: optional, grounded only in manifests, reports, logs, and artifacts.

### Backend requirements

- Store paper manifests, runs, reports, logs, and artifacts.
- Support cached runs for public demo.
- Support controlled live runs for whitelisted toy/gold-set experiments.
- Support local/self-hosted onboarding for a new `(arxiv_id, github_url, commit?)`.
- Generate draft manifests from repository scanning and claim extraction.
- Let users review and edit unresolved manifest fields before execution.
- Maintain provenance for every claim and every run.
- Separate scientific failure from infrastructure failure.
- Expose MCP tools for local agent use, but make the web dashboard the primary showcase.

### New paper onboarding requirements

The product must have a path for new papers, even if the public demo disables arbitrary execution:

1. `claimbench ingest --arxiv-id <id> --repo-url <url> --commit <sha?>`
2. Clone or inspect the repository in a sandboxed workspace.
3. Detect setup files: `requirements.txt`, `environment.yml`, `pyproject.toml`, `setup.py`, `Dockerfile`.
4. Detect likely entrypoints: `train.py`, `eval.py`, `main.py`, notebooks, shell scripts, examples, README commands.
5. Extract candidate numeric/comparison claims from the paper.
6. Link claims to candidate commands and metric parsers.
7. Emit a draft `ClaimManifest` with confidence scores and unresolved fields.
8. Validate the manifest and refuse execution if required fields are missing.
9. Run only reviewed/approved experiments.

This is the difference between a real product and a hardcoded demo.

### Key design decisions

| Decision | Recommendation | Why |
|---|---|---|
| Product surface | Hugging Face Space dashboard first, MCP second | Recruiters can use the dashboard without local setup |
| Demo mode | Cached/precomputed runs by default | Fast, cheap, reliable public demo |
| Live execution | Whitelisted lightweight experiments only | Avoid security and compute-cost risk |
| Domain | Small ML classification / lightweight NLP fine-tuning | Strong ML signal with manageable compute |
| MVP corpus | 3 gold-set papers + one unseen-paper onboarding smoke test | Proves the system is not hardcoded |
| Core artifact | `ClaimManifest` / `PaperManifest` | Makes the system auditable and reproducible |
| Sandbox layer | Docker locally; hosted live mode optional via Modal/E2B/RunPod | Local reproducibility first, cloud execution later |
| UI stack | Gradio or Streamlit on Hugging Face Spaces | Fastest path to a usable demo |
| Backend | FastAPI + SQLite for local; optional Postgres/object storage for hosted | Simple but production-shaped |
| MCP framework | Official Python MCP SDK | Agent interface for Claude/Cursor/local users |
| Reports | Markdown first, HTML optional | Easy to inspect, version, and render |
| Security model | No arbitrary public repo execution | Critical for hosted demo safety |

### MVP success definition

By the end, the project is successful if it can:

1. Host a public Hugging Face Space that a recruiter can use without setup.
2. Show 3 curated papers with claim-level reproducibility status.
3. Verify at least one numeric or comparison claim per paper.
4. Provide cached run evidence: command, environment, dataset, logs, metric output, artifacts.
5. Generate a reproducibility report per paper.
6. Run a local new-paper onboarding flow that produces a validated draft manifest for at least one unseen paper.
7. Expose local MCP tools for agent-based verification.
8. Include one optional live lightweight run if hosting/security budget allows.

Stretch goals:

- Add 5-8 held-out papers for evaluation.
- Support controlled parameter variations for 1-2 papers.
- Add hosted live execution using Modal, E2B, RunPod, or a locked-down VM.
- Add comparison against a Paper2Agent-style tutorial-agent baseline.

---

## 3. Architecture

```text
Hugging Face Space
  Gradio/Streamlit dashboard
  - paper selector
  - claims table
  - verify/replay claim
  - logs/evidence/report tabs
        |
        | HTTP/API calls
        v
ClaimBench API
  FastAPI service or in-process Space backend
  - papers
  - claims
  - runs
  - reports
  - agent Q&A
        |
        +--> Manifest Store
        |      JSON + SQLite
        |      claims, environments, provenance
        |
        +--> Run Manager
        |      cached + live execution
        |      state machine, logs, artifacts
        |
        +--> Report Generator
        |      markdown / HTML
        |      claim summaries, failure taxonomy
        |
        +--> Local Docker sandbox
        |      whitelisted execution only
        |
        +--> MCP Server
               local agent use through Claude/Cursor
```

### Core artifact: `ClaimManifest`

The `ClaimManifest` / `PaperManifest` is the center of the project. It is the contract between the dashboard, experiment runner, report generator, and MCP tools. Treat it like an API, not a temporary JSON dump.

Minimum fields:

- `paper`: arXiv ID, title, repo URL, commit SHA, domain, license, selected hardware profile.
- `claims`: extracted claims with paper location, type, expected metric, tolerance, confidence, and evidence snippet.
- `experiments`: runnable commands with entrypoint, args, expected outputs, metric parser, dataset refs, and linked claim IDs.
- `environment`: base image, Python/CUDA/PyTorch versions, dependency files, generated Dockerfile path, image digest.
- `datasets`: source, expected size/hash when available, local cache key, access requirements.
- `cached_runs`: precomputed run IDs, logs, metrics, artifacts, and public-demo replay metadata.
- `provenance`: extraction model/version, prompt version, parser version, timestamps, manual edits.
- `validation`: schema errors, unresolved fields, human-review status, and uncertainty notes.

If a claim cannot be linked to a command and metric parser, it should be marked `unverified_candidate`, not silently included as reproducible.

### Data model

- `Paper(id, arxiv_id, repo_url, title, domain)`
- `Claim(id, paper_id, text, location, claim_type, expected_metric, tolerance, confidence, status)`
- `Experiment(id, paper_id, entrypoint, args, datasets[], expected_metrics{}, metric_parser, linked_claim_ids[])`
- `Environment(id, paper_id, image_digest, lockfile, dockerfile_path, gpu_required, build_status)`
- `Run(id, experiment_id, env_id, params_override, status, metrics, log_uri, artifact_uri, cost_estimate, started_at, finished_at)`
- `Report(id, paper_id, run_ids[], reproduced_claims, failed_claims, failure_taxonomy, generated_at)`
- `Artifact(id, run_id, kind, uri, sha256, preview_uri)`

Run status enum:

`queued -> preparing -> building_env -> resolving_data -> running -> parsing_metrics -> succeeded|failed|timed_out|cancelled`

Every state transition should be persisted. This is the difference between a serious system and a demo script.

### Dashboard actions

| Action | Input | Output |
|---|---|---|
| Select paper | `paper_id` | summary, claims, prior runs |
| Verify claim | `claim_id` | cached or live `run_id` |
| View evidence | `run_id` | command, logs, metrics, artifacts |
| Generate report | `paper_id` | markdown/HTML report |
| Ask agent | question + selected paper | grounded answer with citations to manifest/report/logs |

### MCP tool surface

MCP is for technical users and local agent workflows, not the primary recruiter demo.

| Tool | Args | Returns |
|---|---|---|
| `list_papers` | none | `[PaperSummary]` |
| `list_claims` | `paper_id` | `[Claim]` |
| `get_manifest` | `paper_id` | validated manifest summary |
| `verify_claim` | `claim_id, mode?` | `{run_id, verdict, observed, expected, tolerance}` |
| `get_run_status` | `run_id` | status enum |
| `get_run_results` | `run_id` | metrics dict + artifact URIs |
| `get_run_logs` | `run_id, tail?` | log text |
| `generate_report` | `paper_id` | reproducibility report URI / markdown |
| `run_variation` | `experiment_id, overrides` | `run_id` |

### Security and isolation requirements

This project runs untrusted GitHub code. That is not a detail; it is one of the main engineering challenges.

- Run every repo inside a container or sandbox, never directly on the host.
- Mount datasets read-only when possible.
- Do not pass host secrets into the sandbox by default.
- Apply runtime, CPU, memory, disk, and optional GPU limits.
- Disable or restrict network access during experiment execution unless a dataset download step explicitly needs it.
- Record repo commit SHA, generated Dockerfile, dependency lockfile, and image digest for every run.
- Treat install scripts and dataset download scripts as untrusted code.
- Surface security limitations honestly in the report.

### Reliability requirements

- Use deterministic IDs for papers, experiments, environments, and runs.
- Make ingestion idempotent: re-ingesting the same `(arxiv_id, repo_url, commit)` should update or reuse existing records predictably.
- Cap automatic dependency repair attempts. Each attempted fix must be logged with stderr, proposed change, and result.
- Separate infrastructure failure from scientific failure. A failed dependency install is not a failed paper claim.
- Prefer explicit failure states over generic exceptions.

---

## 4. 10-Week Plan

### Week 1: Product spec, paper selection, and demo contract

- [x] Freeze product name and one-line positioning: `ClaimBench: Reproducibility Auditor for ML Papers`.
- [x] Select 3 gold-set papers from one domain. Initial domain: time series classification.
- [x] For each paper, identify 2-4 candidate claims from tables or result sections.
- [x] Filter claims to those with public code, clear metric, clear dataset, and feasible CPU/single-GPU execution.
- [x] Define the exact Hugging Face demo flow: paper selector, claims table, evidence panel, report tab, optional agent Q&A.
- [x] Define `ClaimManifest` schema and validation rules.
- [x] Deliverable: product spec, 3 selected papers, claim inventory, first manually written manifest.

Senior-engineering bar: if a claim cannot be tied to a command, metric parser, and expected value, it is not part of the MVP.

### Week 2: Manifest system and static dashboard prototype

- [x] Implement manifest schema using Pydantic or JSON Schema.
- [x] Create manually reviewed manifests for the 3 gold-set papers.
- [x] Implement `claimbench validate-manifest <path>`.
- [x] Implement `claimbench init-paper --arxiv-id <id> --repo-url <url> --commit <sha?>` to create a draft manifest skeleton.
- [x] Implement first repository scanner:
  - setup files
  - likely entrypoints
  - README commands
  - available result files
- [x] Implement a small local data store: manifests, claims, runs, reports, artifacts.
- [x] Build a static Gradio/Streamlit dashboard that loads manifests and renders:
  - paper summary
  - claim table
  - expected metrics
  - placeholder observed metrics
  - report preview
- [x] Add manifest validation tests and fixture examples.
- [x] Deliverable: local dashboard showing the final user experience with static data, plus a CLI path that can initialize and validate a new paper manifest skeleton.

Senior-engineering bar: make the UI usable early, but do not fake the backend contract. The dashboard must read real manifest files, and new paper onboarding must produce the same manifest format as the curated examples.

### Week 3: Reproducibility runner for one paper

- [ ] Pick the easiest gold-set paper as the first end-to-end target.
- [ ] Build the local Docker execution path for that paper.
- [x] Add ROCKET single-dataset wrapper script compatible with the manifest command.
- [x] Capture command, stdout/stderr logs, exit code, runtime, environment metadata, and artifacts.
- [x] Implement metric parser for one claim.
- [ ] Store run result in the run database.
- [x] Implement verdict calculation: expected vs. observed vs. tolerance.
- [x] Ensure runner operates from `ClaimManifest`, not paper-specific Python branches.
- [ ] Deliverable: one claim verified end-to-end locally with stored logs and metrics.

Senior-engineering bar: do not continue to more papers until one claim has a complete evidence chain.

### Week 4: Reports and evidence model

- [ ] Implement reproducibility report generator.
- [ ] Report sections:
  - paper metadata
  - repo commit
  - dataset provenance
  - environment summary
  - claim-by-claim verdicts
  - command and metric parser
  - logs/artifacts
  - failure taxonomy
  - limitations
- [ ] Add report rendering to the dashboard.
- [ ] Add artifact previews where possible: plots, JSON metrics, small log excerpts.
- [ ] Deliverable: first complete reproducibility report for one paper.

Senior-engineering bar: the report is the main portfolio artifact. It must be readable by a recruiter and credible to an engineer.

### Week 5: Extend to 3 gold-set papers

- [ ] Repeat runner setup for papers 2 and 3.
- [ ] Verify at least one claim per paper.
- [ ] Refactor any paper-specific runner logic into manifest-driven adapters.
- [ ] Include at least one partial/failure case if possible; success-only demos look less serious.
- [ ] Normalize failure taxonomy across papers.
- [ ] Add cached run snapshots for all demo claims.
- [ ] Deliverable: 3-paper dashboard with real expected/observed metrics and evidence.

Senior-engineering bar: three solid examples are better than ten weak ones. Keep the scope small and polished.

### Week 6: Public Hugging Face Space

- [ ] Package dashboard as a Hugging Face Space.
- [ ] Use cached/precomputed runs as the default public behavior.
- [ ] Add clear UI labels:
  - `Cached demo run`
  - `Live run unavailable for public safety`
  - `Live lightweight run` if implemented
- [ ] Add sample reports and artifacts to the Space.
- [ ] Add basic error handling and loading states.
- [ ] Deliverable: public Hugging Face Space usable by a recruiter without setup.

Senior-engineering bar: public demo must be reliable. A cached demo that always works is better than a live demo that often fails.

### Week 7: Controlled live execution and sandbox hardening

- [ ] Add optional live execution for one tiny whitelisted experiment.
- [ ] Enforce resource limits: runtime, memory, disk, CPU, network policy.
- [ ] Prevent arbitrary repo URLs in hosted mode.
- [ ] Add run queue/state machine:
  - `queued`
  - `preparing`
  - `running`
  - `parsing_metrics`
  - `succeeded`
  - `failed`
  - `timed_out`
  - `cancelled`
- [ ] Persist every state transition.
- [ ] Deliverable: one safe live claim verification path, or a documented decision to keep hosted mode replay-only.

Senior-engineering bar: security and cost controls are not optional if public users can trigger compute.

### Week 8: MCP interface and agent Q&A

- [ ] Implement local MCP tools:
  - `list_papers`
  - `list_claims`
  - `get_manifest`
  - `verify_claim`
  - `get_run_status`
  - `get_run_results`
  - `get_run_logs`
  - `generate_report`
- [ ] Add local setup instructions for Claude/Cursor MCP integration.
- [ ] Add optional dashboard Q&A grounded in manifests, reports, logs, and artifacts.
- [ ] Make Q&A refuse unsupported claims instead of hallucinating.
- [ ] Deliverable: local agent can verify a claim through MCP; dashboard can answer grounded questions.

Senior-engineering bar: MCP is a power-user feature. The public product should still be useful without MCP.

### Week 9: Evaluation and comparison

- [ ] Evaluate the 3 gold-set papers:
  - number of candidate claims
  - number of executable claims
  - number reproduced within tolerance
  - number failed and why
- [ ] Run one unseen-paper onboarding smoke test:
  - generate draft manifest
  - detect repository setup files
  - detect candidate commands
  - extract or manually enter 1-2 candidate claims
  - report unresolved fields
  - do not require full reproduction if infeasible
- [ ] Measure engineering metrics:
  - time to first successful run
  - environment build success
  - run success
  - cost/runtime
  - failure categories
- [ ] Compare against baselines:
  - raw README + repo
  - manually written manifest
  - generated/assisted manifest
  - optional Paper2Agent-style tutorial-agent framing
- [ ] Deliverable: evaluation section and charts/tables for README/report, including evidence that the system can initialize a new paper rather than only replay hardcoded examples.

Senior-engineering bar: measure what failed. Honest failure analysis makes the project stronger, not weaker.

### Week 10: Portfolio polish and launch

- [ ] Polish Hugging Face Space landing text.
- [ ] Record 2-3 minute demo video:
  - select paper
  - inspect claims
  - verify claim
  - inspect logs/evidence
  - open report
  - mention MCP/local agent path
- [ ] Write GitHub README:
  - problem
  - demo link
  - architecture
  - how it differs from Paper2Agent
  - evaluation results
  - limitations
  - local MCP setup
- [ ] Add tests and CI badge.
- [ ] Write short technical blog post: `What breaks when agents try to reproduce ML papers?`
- [ ] Deliverable: public demo, GitHub repo, demo video, reports, and portfolio-ready README.

Senior-engineering bar: a recruiter should understand the project in 60 seconds; an ML infra engineer should respect it after reading the README.

---

## 5. Evaluation and Research Contribution

The contribution is not "I built another paper agent." The contribution is a reproducibility audit layer:

1. **Claim executability**: what fraction of paper claims can be tied to an executable command and metric parser?
2. **Claim reproduction**: when executable, do the observed metrics match the paper within tolerance?
3. **Failure diagnosis**: when reproduction fails, is the cause dependency drift, missing data, hardware mismatch, nondeterminism, unclear hyperparameters, code bugs, or metric parsing?
4. **Agent trust**: does an agent with ClaimBench evidence answer paper questions more accurately than an agent with only the raw repo/README?
5. **Audit usability**: can a non-expert understand why a paper is reproduced, partially reproduced, or failed?

Tie the discussion to **CORE-Bench**, Paper2Agent, Papers with Code, ReproZip, CodeOcean, and reproducibility studies. Position ClaimBench as a complementary verification layer, not a duplicate.

### Evaluation table to produce

The final report should include at least:

| Metric | Why it matters |
|---|---|
| Candidate claims per paper | Shows paper complexity and audit coverage |
| Executable claims per paper | Measures how much of the paper can actually be tested |
| Claim reproduction rate | Main trust signal |
| Manifest validity rate | Shows structured extraction quality |
| Environment build success rate | Measures real engineering difficulty |
| Time to first successful run | Practical usability metric |
| Cost/runtime per verification | Important for hosted and agent use |
| Failure taxonomy distribution | Shows research maturity and honest analysis |
| Agent answer quality with vs. without ClaimBench evidence | Shows value beyond a dashboard |

### Strong case studies

Pick 2-3 case studies and write them deeply:

1. **Clean success**: a claim is reproduced with expected metric, observed metric, logs, artifacts, and report.
2. **Partial failure**: the repo builds and experiment runs, but the metric differs. Explain whether the issue is nondeterminism, undocumented hyperparameters, dataset version, or hardware.
3. **Audit value**: an agent answers a paper question better when grounded in ClaimBench evidence than when reading only the README.

These case studies will matter more for portfolio review than a large but shallow benchmark.

---

## 6. Product and Portfolio Bar

This project must feel like a shipped system, not a class assignment.

### Demo user journey

The demo should show:

1. Open the Hugging Face Space.
2. Select one curated paper.
3. See paper metadata, repo commit, dataset, and reproducibility score.
4. Open the claims table.
5. Select one claim and click `Verify Claim`.
6. See cached or live run status.
7. Compare expected vs. observed metrics.
8. Inspect command, environment, logs, metric parser output, and artifacts.
9. Open the reproducibility report.
10. Optionally ask a grounded question about the paper's reproducibility.

### Recruiter / hiring-manager artifacts

- 2-3 minute demo video.
- Polished README with architecture diagram and quickstart.
- Example `ClaimManifest` / `PaperManifest` files.
- Example reproducibility reports.
- Clear limitations section.
- Evaluation results with failure taxonomy.
- Tests and CI badge.
- Short technical blog post: "What breaks when agents try to reproduce ML papers?"

### Resume positioning

Possible resume bullet:

> Built ClaimBench, a claim-level reproducibility auditor for ML papers that verifies reported results from public code, runs sandboxed experiments, tracks metrics/logs/artifacts, and generates failure-aware reproducibility reports through a Hugging Face dashboard and MCP tools.

This is stronger than saying "built an MCP server for research papers" because it emphasizes trust, verification, ML reproducibility, safety, and evaluation.

---

## 7. Risks & Cut List

| Risk | Mitigation |
|---|---|
| Dep resolution is a tar pit | Choose papers with runnable examples; strict timeout per paper |
| GPU access/cost | Target CPU-feasible papers; use cached public runs |
| Claim extraction quality | Hand-annotate 5 papers as ground truth early; iterate prompt against that |
| Scope creep on variations | Cut variations before cutting reports |
| MCP spec drift | Pin specific SDK version; don't chase main |
| Security concerns from arbitrary code execution | Run repos only in isolated containers/sandboxes with resource caps and no default secrets |
| Demo looks like a wrapper | Lead with the dashboard, evidence chain, reports, evaluation, and failure taxonomy |
| Too many papers, too little depth | Prioritize 3 excellent gold-set papers over 20 weak examples |

**Hard rule**: if end of Week 6 and no paper runs end-to-end, cut to 1-2 papers and make the dashboard/report quality excellent.

**Second hard rule**: if automatic ingestion is weak, allow manually reviewed manifests. A credible semi-automated system with excellent execution is better than a magical fully automated system that fails unpredictably.

---

## 8. Research Framing

Do not position this as only engineering. Position it as: **"Claim-level verification for agentic scientific reproduction."** Target venues:
- NeurIPS ML Reproducibility Workshop
- ICLR Blog Track
- MLSys artifact track

The interesting question is not only whether an LLM can use a paper's tools. It is whether we can trust the evidence behind the paper agent's answers.

For industry, position it slightly differently depending on company:

- **Anthropic / OpenAI**: agent evaluation, tool-use reliability, grounded answers, uncertainty handling.
- **Google / Meta**: ML infrastructure, reproducibility, experiment systems, dataset/environment management.
- **Amazon**: production execution, cost controls, operational reliability, customer-facing automation.
- **Research engineer roles**: bridging papers, code, experiments, and reproducible evidence.

---

## 9. Engineering Quality Bar

This is the section that prevents the project from looking childish.

- No hidden manual steps in the main demo. If a step is manual, label it as manual in provenance.
- No vague "AI extracts claims" without schema validation, confidence, and human-review status.
- No arbitrary repo execution on the host machine.
- No screenshots-only results. Every result should have a stored run record, logs, metric parser output, and artifact path.
- No success-only reporting. Failed reproductions are valuable if the failure reason is precise.
- No huge unsupported claims like "reproduces any paper." Say "selected ML papers with public code."
- No overbuilt UI before the backend is credible. A simple dashboard plus good reports is enough.
- No dependency on one lucky paper. The system should show at least 3 credible examples or clearly explain why not.

Minimum test plan:

- Unit tests for manifest schema validation.
- Unit tests for claim/metric parsing on fixed fixtures.
- Unit tests for repo scanner detection.
- Unit tests for run state transitions.
- Integration test using a tiny toy repo that trains/evaluates quickly.
- Dashboard smoke test: load paper, select claim, replay run, render report.
- MCP tool smoke test: list claims, verify claim, poll status, fetch results.

---

## 10. Working Notes / Decisions Log

<!-- Append as decisions are made during implementation. Format:
YYYY-MM-DD - decision - rationale
-->

- 2026-04-22 - Plan drafted (v1).
- 2026-05-02 - Plan revised toward portfolio-grade MVP: narrowed corpus, added `PaperManifest`, security, reliability, evaluation, reporting, and hiring signal.
- 2026-05-03 - Plan pivoted to ClaimBench: a Hugging Face reproducibility audit dashboard with MCP as a secondary agent interface.

---

## 11. Open Questions

- Which exact 3 papers form the gold set?
- Which domain to commit to? Recommended default: small ML classification / lightweight NLP fine-tuning.
- Should the public Hugging Face demo be cached-only, or include one live lightweight run?
- Is Docker-only enough for local v1, with Modal/E2B/RunPod as a stretch goal?
- Do we need a vector store for paper text, or is full-context plus section retrieval sufficient?
- How to handle papers with multiple repos (author + community fork)?
- What is the minimum acceptable report format: markdown only, or markdown plus static HTML?
