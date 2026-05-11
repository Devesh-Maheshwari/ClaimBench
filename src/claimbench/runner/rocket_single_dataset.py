"""ROCKET single-dataset execution helpers.

This module adapts the official ROCKET implementation to ClaimBench's metric
output contract. It deliberately expects the official repository code and UCR
data to be supplied externally rather than vendoring paper code into ClaimBench.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RocketRunError(Exception):
    """Raised when a ROCKET run cannot be completed."""


@dataclass(frozen=True)
class UCRDataset:
    """Loaded UCR train/test arrays."""

    x_train: Any
    y_train: Any
    x_test: Any
    y_test: Any


def resolve_ucr_files(data_root: Path, dataset: str) -> tuple[Path, Path]:
    """Resolve common UCR TSV layouts for a dataset."""

    candidates = [
        (
            data_root / dataset / f"{dataset}_TRAIN.tsv",
            data_root / dataset / f"{dataset}_TEST.tsv",
        ),
        (
            data_root / f"{dataset}_TRAIN.tsv",
            data_root / f"{dataset}_TEST.tsv",
        ),
    ]
    for train_path, test_path in candidates:
        if train_path.exists() and test_path.exists():
            return train_path, test_path
    raise RocketRunError(f"Could not find UCR train/test TSV files for dataset: {dataset}")


def load_ucr_tsv(path: Path) -> tuple[Any, Any]:
    """Load a UCR TSV file as labels and float32 time-series values."""

    try:
        import numpy as np
    except ImportError as exc:
        raise RocketRunError("numpy is required to load UCR data") from exc

    data = np.loadtxt(path, delimiter="\t")
    if data.ndim == 1:
        data = data.reshape(1, -1)
    labels = data[:, 0]
    values = data[:, 1:].astype(np.float32)
    return values, labels


def load_ucr_dataset(data_root: Path, dataset: str) -> UCRDataset:
    """Load train/test splits for a UCR dataset."""

    train_path, test_path = resolve_ucr_files(data_root, dataset)
    x_train, y_train = load_ucr_tsv(train_path)
    x_test, y_test = load_ucr_tsv(test_path)
    return UCRDataset(x_train=x_train, y_train=y_train, x_test=x_test, y_test=y_test)


def run_rocket_single_dataset(
    *,
    dataset: str,
    data_root: Path,
    rocket_code_path: Path,
    num_kernels: int,
    output_path: Path,
) -> dict[str, Any]:
    """Run official ROCKET functions on one UCR dataset and write metrics."""

    try:
        import numpy as np
        from sklearn.linear_model import RidgeClassifierCV
        from sklearn.metrics import accuracy_score
    except ImportError as exc:
        raise RocketRunError("numpy and scikit-learn are required for ROCKET runs") from exc

    if not rocket_code_path.exists():
        raise RocketRunError(f"ROCKET code path does not exist: {rocket_code_path}")

    sys.path.insert(0, str(rocket_code_path.resolve()))
    try:
        from rocket_functions import apply_kernels, generate_kernels
    except ImportError as exc:
        raise RocketRunError(
            "Could not import rocket_functions from official ROCKET code path: "
            f"{exc}"
        ) from exc

    loaded = load_ucr_dataset(data_root, dataset)
    started = time.monotonic()

    kernels = generate_kernels(loaded.x_train.shape[-1], num_kernels)
    x_train_transform = apply_kernels(loaded.x_train, kernels)
    classifier = _ridge_classifier(np)
    classifier.fit(x_train_transform, loaded.y_train)

    x_test_transform = apply_kernels(loaded.x_test, kernels)
    predictions = classifier.predict(x_test_transform)
    accuracy = float(accuracy_score(loaded.y_test, predictions))
    runtime_seconds = time.monotonic() - started

    metrics = {
        "dataset": dataset,
        "accuracy": accuracy,
        "runtime_seconds": runtime_seconds,
        "num_kernels": num_kernels,
        "num_train": int(loaded.x_train.shape[0]),
        "num_test": int(loaded.x_test.shape[0]),
        "rocket_code_path": str(rocket_code_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def _ridge_classifier(np_module: Any) -> Any:
    """Create a RidgeClassifierCV across sklearn versions."""

    from sklearn.linear_model import RidgeClassifierCV

    alphas = np_module.logspace(-3, 3, 10)
    try:
        return RidgeClassifierCV(alphas=alphas, normalize=True)
    except TypeError:
        return RidgeClassifierCV(alphas=alphas)
