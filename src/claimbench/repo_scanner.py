"""Repository scanning utilities for new-paper onboarding."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


SETUP_PATTERNS = (
    "requirements.txt",
    "requirements-dev.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Dockerfile",
)

ENTRYPOINT_NAMES = (
    "train.py",
    "eval.py",
    "evaluate.py",
    "test.py",
    "main.py",
    "run.py",
)

RESULT_PATTERNS = (
    "*.csv",
    "*.json",
    "*.jsonl",
    "*.txt",
)


@dataclass(frozen=True)
class RepoScanResult:
    """Summary of files relevant to reproducing a paper repository."""

    repo_path: str
    setup_files: list[str]
    entrypoints: list[str]
    notebooks: list[str]
    shell_scripts: list[str]
    result_files: list[str]
    readme_files: list[str]
    readme_commands: list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _relative_matches(root: Path, pattern: str) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob(pattern) if path.is_file())


def scan_repository(repo_path: Path) -> RepoScanResult:
    """Scan a local repository for files useful during manifest generation."""

    root = repo_path.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Repository path does not exist or is not a directory: {repo_path}")

    setup_files: list[str] = []
    for pattern in SETUP_PATTERNS:
        setup_files.extend(_relative_matches(root, pattern))

    entrypoints: list[str] = []
    for name in ENTRYPOINT_NAMES:
        entrypoints.extend(_relative_matches(root, name))

    result_files: list[str] = []
    for pattern in RESULT_PATTERNS:
        result_files.extend(
            path for path in _relative_matches(root, pattern) if _looks_like_result_path(path)
        )

    readme_files = _readme_files(root)

    return RepoScanResult(
        repo_path=str(root),
        setup_files=sorted(set(setup_files)),
        entrypoints=sorted(set(entrypoints)),
        notebooks=_relative_matches(root, "*.ipynb"),
        shell_scripts=_relative_matches(root, "*.sh"),
        result_files=sorted(set(result_files)),
        readme_files=readme_files,
        readme_commands=_extract_readme_commands(root, readme_files),
    )


def _looks_like_result_path(path: str) -> bool:
    lowered = path.lower()
    return any(
        marker in lowered
        for marker in ("result", "metric", "accuracy", "benchmark", "score", "eval")
    )


def _extract_readme_commands(root: Path, readme_files: list[str]) -> list[str]:
    commands: list[str] = []
    prefixes = ("python ", "python3 ", "pip ", "conda ", "docker ", "bash ", "sh ")

    for relative_path in readme_files:
        path = root / relative_path
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(errors="ignore").splitlines()

        in_code_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            normalized = stripped.removeprefix("$ ").removeprefix("> ")
            if in_code_block and normalized.startswith(prefixes):
                commands.append(normalized)

    return sorted(set(commands))


def _readme_files(root: Path) -> list[str]:
    seen: set[Path] = set()
    readmes: list[str] = []

    for path in root.rglob("*"):
        if not path.is_file() or path.name.lower() != "readme.md":
            continue

        resolved = path.resolve()
        if resolved in seen:
            continue

        seen.add(resolved)
        readmes.append(str(path.relative_to(root)))

    return sorted(readmes)
