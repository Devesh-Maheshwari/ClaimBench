"""Generic repository workspace preparation for audits."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Type

from claimbench.audit.errors import AuditRecipeError


def clone_or_update_repo(
    *,
    code_url: str,
    repo_dir: Path,
    code_commit: str | None,
    error_cls: Type[Exception] = AuditRecipeError,
) -> None:
    """Clone or fetch a git repository into ``repo_dir`` and optionally checkout a commit."""

    if repo_dir.exists():
        command = ["git", "-C", str(repo_dir), "fetch", "--all", "--tags"]
    else:
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone", code_url, str(repo_dir)]
    try:
        subprocess.run(command, check=True)

        if code_commit:
            subprocess.run(["git", "-C", str(repo_dir), "checkout", code_commit], check=True)
    except subprocess.CalledProcessError as exc:
        raise error_cls(f"Could not prepare code repository: {' '.join(exc.cmd)}") from exc
