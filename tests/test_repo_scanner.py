from __future__ import annotations

from pathlib import Path

from claimbench.repo_scanner import scan_repository


def test_scan_repository_detects_reproduction_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "\n".join(
            [
                "# Demo Repo",
                "",
                "```bash",
                "pip install -r requirements.txt",
                "python eval.py --dataset Coffee",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    (tmp_path / "eval.py").write_text("print('eval')\n", encoding="utf-8")
    (tmp_path / "results_accuracy.csv").write_text("accuracy\n0.9\n", encoding="utf-8")
    (tmp_path / "analysis.ipynb").write_text("{}", encoding="utf-8")
    (tmp_path / "run.sh").write_text("python eval.py\n", encoding="utf-8")

    result = scan_repository(tmp_path)

    assert result.setup_files == ["requirements.txt"]
    assert result.entrypoints == ["eval.py"]
    assert result.notebooks == ["analysis.ipynb"]
    assert result.shell_scripts == ["run.sh"]
    assert result.result_files == ["results_accuracy.csv"]
    assert result.readme_files == ["README.md"]
    assert result.readme_commands == [
        "pip install -r requirements.txt",
        "python eval.py --dataset Coffee",
    ]
