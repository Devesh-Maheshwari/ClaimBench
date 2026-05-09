from __future__ import annotations

from pathlib import Path

import pytest

from claimbench.runner.rocket_single_dataset import (
    RocketRunError,
    load_ucr_dataset,
    resolve_ucr_files,
    run_rocket_single_dataset,
)


def _write_ucr_dataset(root: Path, dataset: str) -> None:
    dataset_dir = root / dataset
    dataset_dir.mkdir(parents=True)
    (dataset_dir / f"{dataset}_TRAIN.tsv").write_text(
        "1\t0.1\t0.2\t0.3\n2\t0.4\t0.5\t0.6\n",
        encoding="utf-8",
    )
    (dataset_dir / f"{dataset}_TEST.tsv").write_text(
        "1\t0.1\t0.2\t0.3\n2\t0.4\t0.5\t0.6\n",
        encoding="utf-8",
    )


def test_resolve_ucr_files_nested_layout(tmp_path: Path) -> None:
    _write_ucr_dataset(tmp_path, "Coffee")

    train_path, test_path = resolve_ucr_files(tmp_path, "Coffee")

    assert train_path.name == "Coffee_TRAIN.tsv"
    assert test_path.name == "Coffee_TEST.tsv"


def test_load_ucr_dataset_shapes(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    _write_ucr_dataset(tmp_path, "Coffee")

    dataset = load_ucr_dataset(tmp_path, "Coffee")

    assert dataset.x_train.shape == (2, 3)
    assert dataset.x_test.shape == (2, 3)
    assert dataset.y_train.tolist() == [1.0, 2.0]


def test_run_rocket_requires_official_code_path(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    _write_ucr_dataset(tmp_path, "Coffee")

    with pytest.raises(RocketRunError, match="ROCKET code path does not exist"):
        run_rocket_single_dataset(
            dataset="Coffee",
            data_root=tmp_path,
            rocket_code_path=tmp_path / "missing_rocket" / "code",
            num_kernels=10,
            output_path=tmp_path / "metrics.json",
        )
