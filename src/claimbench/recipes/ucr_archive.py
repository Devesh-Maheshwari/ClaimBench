"""UCR Time Series Classification Archive 2018 dataset preparation (recipe-specific)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from claimbench.audit.errors import AuditRecipeError

UCR_ARCHIVE_2018_URL = (
    "https://zenodo.org/api/records/11198697/files/"
    "UCR%20Archive%202018.zip/content"
)


def prepare_ucr_dataset(
    *,
    output_dir: Path,
    dataset: str,
    archive_url: str = UCR_ARCHIVE_2018_URL,
) -> dict[str, Any]:
    """Download the UCR archive if needed and extract one dataset's TRAIN/TEST TSV files."""

    dataset_dir = output_dir / "data" / "UCR" / dataset
    train_path = dataset_dir / f"{dataset}_TRAIN.tsv"
    test_path = dataset_dir / f"{dataset}_TEST.tsv"
    if train_path.exists() and test_path.exists():
        return {
            "status": "already_present",
            "dataset": dataset,
            "dataset_dir": dataset_dir,
            "train_path": train_path,
            "test_path": test_path,
        }

    downloads_dir = output_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    archive_path = downloads_dir / "ucr_archive_2018.zip"
    if not archive_path.exists():
        urlretrieve(archive_url, archive_path)

    dataset_dir.mkdir(parents=True, exist_ok=True)
    extracted = _extract_ucr_dataset(
        archive_path=archive_path,
        dataset=dataset,
        train_path=train_path,
        test_path=test_path,
    )
    summary = {
        "status": "extracted",
        "dataset": dataset,
        "archive_url": archive_url,
        "archive_path": archive_path,
        "dataset_dir": dataset_dir,
        "train_path": train_path,
        "test_path": test_path,
        "extracted_members": extracted,
    }
    (output_dir / "data_prep.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


def _extract_ucr_dataset(
    *,
    archive_path: Path,
    dataset: str,
    train_path: Path,
    test_path: Path,
) -> list[str]:
    needed = {
        f"{dataset}_TRAIN.tsv": train_path,
        f"{dataset}_TEST.tsv": test_path,
    }
    extracted: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            member_name = Path(member).name
            if member_name not in needed:
                continue
            target_path = needed[member_name]
            target_path.write_bytes(archive.read(member))
            extracted.append(member)

    missing = [name for name, path in needed.items() if not path.exists()]
    if missing:
        raise AuditRecipeError(
            f"Could not find {dataset} files in UCR archive: {', '.join(missing)}"
        )
    return extracted
