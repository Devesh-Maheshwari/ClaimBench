from __future__ import annotations

from claimbench.manifest import load_manifest
from claimbench.paths import EXAMPLE_MANIFESTS_ROOT
from claimbench.storage.cached_runs import load_cached_run_results


def test_cached_runs_convert_to_runner_results() -> None:
    manifest = load_manifest(EXAMPLE_MANIFESTS_ROOT / "rocket_1910_13051.manifest.json")

    results = load_cached_run_results(manifest)

    assert [result.experiment_id for result in results] == [
        "rocket_exp_ucr_reduced",
        "rocket_exp_single_dataset",
    ]
    assert results[0].status == "succeeded"
    assert results[0].observed_metric == 438.2
    assert results[0].runtime_seconds == 438.2
    assert results[1].observed_metric == 1.0
    assert results[1].verdicts[0].status == "needs_review"


def test_cached_runs_are_loaded_for_all_gold_manifests() -> None:
    for path in sorted(EXAMPLE_MANIFESTS_ROOT.glob("*.manifest.json")):
        manifest = load_manifest(path)
        assert load_cached_run_results(manifest), path.name
