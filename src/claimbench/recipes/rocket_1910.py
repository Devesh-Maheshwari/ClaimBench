"""ROCKET (arXiv 1910.13051) audit recipe — paper-specific manifest and workspace layout."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from claimbench.audit.workspace import clone_or_update_repo
from claimbench.repo_scanner import scan_repository

RECIPE_ID = "rocket_1910_13051"
# Stable slug returned from ``prepare_audit_manifest`` (matches historical ``audit.py``).
RECIPE_SLUG = "rocket"


def matches(*, paper_url: str, code_url: str) -> bool:
    normalized = f"{paper_url} {code_url}".lower()
    return "1910.13051" in normalized or "angus924/rocket" in normalized


def prepare_audit_manifest(
    *,
    paper_url: str,
    code_url: str,
    output_dir: Path,
    dataset: str = "Coffee",
    num_kernels: int = 1000,
    code_commit: str | None = None,
    clone_repo: bool = True,
) -> dict[str, Any]:
    """Clone official ROCKET repo, write manifest.json and repo_scan.json under ``output_dir``."""

    output_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = output_dir / "workspace" / "rocket"
    if clone_repo:
        clone_or_update_repo(code_url=code_url, repo_dir=repo_dir, code_commit=code_commit)

    manifest = _rocket_manifest_dict(
        paper_url=paper_url,
        code_url=code_url,
        repo_dir=repo_dir,
        output_dir=output_dir,
        dataset=dataset,
        num_kernels=num_kernels,
        code_commit=code_commit,
    )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    scan_path = output_dir / "repo_scan.json"
    if repo_dir.exists():
        scan_path.write_text(scan_repository(repo_dir).to_json() + "\n", encoding="utf-8")

    return {
        "recipe": RECIPE_SLUG,
        "manifest_path": manifest_path,
        "repo_dir": repo_dir,
        "scan_path": scan_path if scan_path.exists() else None,
    }


def _rocket_manifest_dict(
    *,
    paper_url: str,
    code_url: str,
    repo_dir: Path,
    output_dir: Path,
    dataset: str,
    num_kernels: int,
    code_commit: str | None,
) -> dict[str, Any]:
    metrics_path = output_dir / "metrics" / "rocket_single_dataset.json"
    data_root = output_dir / "data" / "UCR"
    paper_id = "rocket_1910_13051_audit"
    return {
        "schema_version": "0.1.0",
        "paper": {
            "paper_id": paper_id,
            "title": "ROCKET: Exceptionally Fast and Accurate Time Series Classification Using Random Convolutional Kernels",
            "arxiv_id": "1910.13051",
            "paper_url": paper_url,
            "repo_url": code_url,
            "repo_commit": code_commit or "unresolved-live-audit",
            "domain": "time_series_classification",
            "license": None,
            "hardware_profile": "cpu",
        },
        "claims": [
            {
                "claim_id": "rocket_claim_single_dataset_pipeline",
                "text": "ROCKET transforms time series with random convolutional kernels and trains a linear classifier for fast classification.",
                "claim_type": "numeric_metric",
                "paper_location": "Method / official implementation",
                "evidence_snippet": "The official implementation exposes generate_kernels and apply_kernels for ROCKET classification experiments.",
                "expected_metric": {
                    "name": "single_dataset_accuracy",
                    "value": "to_be_measured",
                    "unit": "accuracy",
                    "higher_is_better": True,
                },
                "tolerance": {
                    "type": "manual",
                    "value": "dataset-specific",
                    "rationale": "The first audit run measures the selected dataset and records the observed paper-code behavior for review.",
                },
                "linked_experiment_ids": ["rocket_exp_single_dataset"],
                "confidence": 0.75,
                "status": "needs_review",
            }
        ],
        "experiments": [
            {
                "experiment_id": "rocket_exp_single_dataset",
                "name": f"ROCKET single-dataset audit on {dataset}",
                "command": [
                    "python",
                    "scripts/run_rocket_single_dataset.py",
                    "--dataset",
                    dataset,
                    "--num-kernels",
                    str(num_kernels),
                    "--data-root",
                    data_root.as_posix(),
                    "--rocket-code-path",
                    (repo_dir / "code").as_posix(),
                    "--output",
                    metrics_path.as_posix(),
                ],
                "working_directory": ".",
                "expected_runtime_seconds": None,
                "metric_parser": {
                    "type": "json_path",
                    "target": "$.accuracy",
                },
                "linked_claim_ids": ["rocket_claim_single_dataset_pipeline"],
                "dataset_ids": ["ucr_selected_dataset"],
            }
        ],
        "environment": {
            "execution_mode": "docker",
            "base_image": "claimbench/rocket-audit:latest",
            "python_version": "3.10",
            "cuda_version": None,
            "dependency_files": ["config/docker/rocket-audit.Dockerfile"],
            "image_digest": None,
        },
        "datasets": [
            {
                "dataset_id": "ucr_selected_dataset",
                "name": f"UCR {dataset} dataset",
                "source": "https://www.timeseriesclassification.com/",
                "version": None,
                "sha256": None,
                "access_notes": f"Place {dataset}_TRAIN.tsv and {dataset}_TEST.tsv under {data_root / dataset} before live execution.",
            }
        ],
        "cached_runs": [],
        "provenance": {
            "created_by": "claimbench audit-paper",
            "created_at": date.today().isoformat(),
            "extraction_model": None,
            "parser_version": None,
            "manual_edits": [
                "ROCKET MVP recipe generated from paper URL and official code URL.",
                "Expected metric remains to_be_measured until a dataset-specific paper value is locked.",
            ],
            "review_status": "draft",
        },
        "validation": {
            "unresolved_fields": [
                "dataset files",
                "dataset-specific expected accuracy",
                "dependency lockfile",
                "Docker image digest",
            ],
            "notes": "This audit manifest is generated automatically and should be reviewed after the first live run.",
        },
    }
