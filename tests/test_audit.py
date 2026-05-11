from __future__ import annotations

import zipfile
from pathlib import Path

from claimbench.audit import prepare_ucr_dataset


def test_prepare_ucr_dataset_extracts_selected_dataset(tmp_path: Path) -> None:
    archive_path = tmp_path / "source_ucr.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("UCRArchive_2018/Coffee/Coffee_TRAIN.tsv", "1\t0.1\t0.2\n")
        archive.writestr("UCRArchive_2018/Coffee/Coffee_TEST.tsv", "2\t0.3\t0.4\n")
        archive.writestr("UCRArchive_2018/Other/Other_TRAIN.tsv", "1\t9\n")

    output_dir = tmp_path / "audit"
    summary = prepare_ucr_dataset(
        output_dir=output_dir,
        dataset="Coffee",
        archive_url=archive_path.as_uri(),
    )

    assert summary["status"] == "extracted"
    assert (output_dir / "data" / "UCR" / "Coffee" / "Coffee_TRAIN.tsv").read_text(
        encoding="utf-8"
    ) == "1\t0.1\t0.2\n"
    assert (output_dir / "data" / "UCR" / "Coffee" / "Coffee_TEST.tsv").read_text(
        encoding="utf-8"
    ) == "2\t0.3\t0.4\n"
    assert (output_dir / "data_prep.json").exists()


def test_prepare_ucr_dataset_reuses_existing_files(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "audit" / "data" / "UCR" / "Coffee"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "Coffee_TRAIN.tsv").write_text("train\n", encoding="utf-8")
    (dataset_dir / "Coffee_TEST.tsv").write_text("test\n", encoding="utf-8")

    summary = prepare_ucr_dataset(
        output_dir=tmp_path / "audit",
        dataset="Coffee",
        archive_url=(tmp_path / "missing.zip").as_uri(),
    )

    assert summary["status"] == "already_present"
