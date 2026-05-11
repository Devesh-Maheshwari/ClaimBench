from __future__ import annotations

from pathlib import Path
from typing import Any

import claimbench.audit.registry as audit_registry


def test_register_recipe_dispatches_when_default_recipe_does_not_match(tmp_path: Path) -> None:
    """A recipe registered via ``register_recipe`` is used when earlier recipes do not match."""

    class _PluginRecipe:
        def matches(self, *, paper_url: str, code_url: str) -> bool:
            _ = code_url
            return "plugin-audit" in paper_url

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
            _ = paper_url, code_url, dataset, num_kernels, code_commit, clone_repo
            output_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = output_dir / "plugin_manifest.json"
            manifest_path.write_text('{"schema_version": "0.1.0"}\n', encoding="utf-8")
            return {
                "recipe": "dummy_plugin",
                "manifest_path": manifest_path,
                "repo_dir": output_dir / "repo",
                "scan_path": None,
            }

    saved = audit_registry._RECIPES
    try:
        audit_registry.register_recipe(_PluginRecipe())
        out = tmp_path / "plugin_out"
        result = audit_registry.prepare_audit_manifest(
            paper_url="https://example.org/plugin-audit/v1",
            code_url="https://example.org/some/code",
            output_dir=out,
            clone_repo=False,
        )
        assert result["recipe"] == "dummy_plugin"
        assert result["manifest_path"].name == "plugin_manifest.json"
    finally:
        audit_registry._RECIPES = saved
