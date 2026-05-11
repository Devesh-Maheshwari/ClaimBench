"""Recipe selection and dispatch for ``prepare_audit_manifest`` (generic entry point)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from claimbench.audit.errors import AuditRecipeError
from claimbench.recipes import rocket_1910


class AuditRecipe(Protocol):
    """Recipe that can build an audit manifest for a matching paper/repo."""

    def matches(self, *, paper_url: str, code_url: str) -> bool: ...

    def prepare_audit_manifest(
        self,
        *,
        paper_url: str,
        code_url: str,
        output_dir: Path,
        dataset: str,
        num_kernels: int,
        code_commit: str | None,
        clone_repo: bool,
    ) -> dict[str, Any]: ...


class _RocketRecipe:
    def matches(self, *, paper_url: str, code_url: str) -> bool:
        return rocket_1910.matches(paper_url=paper_url, code_url=code_url)

    def prepare_audit_manifest(
        self,
        *,
        paper_url: str,
        code_url: str,
        output_dir: Path,
        dataset: str,
        num_kernels: int,
        code_commit: str | None,
        clone_repo: bool,
    ) -> dict[str, Any]:
        return rocket_1910.prepare_audit_manifest(
            paper_url=paper_url,
            code_url=code_url,
            output_dir=output_dir,
            dataset=dataset,
            num_kernels=num_kernels,
            code_commit=code_commit,
            clone_repo=clone_repo,
        )


_RECIPES: tuple[AuditRecipe, ...] = (_RocketRecipe(),)


def register_recipe(recipe: AuditRecipe) -> None:
    """Register an additional recipe (used by optional plugins or tests)."""

    global _RECIPES
    _RECIPES = _RECIPES + (recipe,)


def _select_recipe(*, paper_url: str, code_url: str) -> AuditRecipe:
    for recipe in _RECIPES:
        if recipe.matches(paper_url=paper_url, code_url=code_url):
            return recipe
    raise AuditRecipeError(
        "No supported audit recipe matched this paper/code pair. "
        "See claimbench.recipes for registered recipes (e.g. ROCKET arXiv 1910.13051)."
    )


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
    """Prepare an audit workspace and manifest using the first matching recipe."""

    recipe = _select_recipe(paper_url=paper_url, code_url=code_url)
    return recipe.prepare_audit_manifest(
        paper_url=paper_url,
        code_url=code_url,
        output_dir=output_dir,
        dataset=dataset,
        num_kernels=num_kernels,
        code_commit=code_commit,
        clone_repo=clone_repo,
    )
