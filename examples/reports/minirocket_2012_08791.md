# ClaimBench Report: MINIROCKET: A Very Fast (Almost) Deterministic Transform for Time Series Classification

- Paper ID: `minirocket_2012_08791`
- arXiv: `2012.08791`
- Repository: `https://github.com/angus924/minirocket`
- Commit: `0b1c245d9c9dbc50886f28bc7b32d5d45b5663d6`
- Overall status: `needs_review`
- Claims: `2`
- Experiment runs: `2`
- Claim status counts: `needs_review=2`
- Experiment status counts: `succeeded=2`
- Failure category counts: `none=2`

## Claims

### `minirocket_claim_full_ucr_runtime`

- Status: `needs_review`
- Expected: `total_runtime_minutes=10 minutes`
- Observed: `12.8`
- Experiments: `minirocket_exp_ucr_reduced`
- Reason: Manual tolerance requires human review.

MINIROCKET can train and test classifiers on all 109 UCR datasets to state-of-the-art accuracy in less than 10 minutes.

### `minirocket_claim_repeatability`

- Status: `needs_review`
- Expected: `repeat_run_accuracy_delta=to_be_measured accuracy_delta`
- Observed: `0.0`
- Experiments: `minirocket_exp_repeatability`
- Reason: Expected value is not locked yet.

MINIROCKET is almost deterministic while maintaining essentially the same accuracy as ROCKET.

## Experiments

### `minirocket_exp_ucr_reduced`

- Status: `succeeded`
- Return code: `0`
- Runtime seconds: `12.8`
- Observed metric: `12.8`
- Failure category: `none`
- Command: `python scripts/run_minirocket_single_dataset.py --dataset Coffee --output ./runs/minirocket_single_dataset/metrics.json`

### `minirocket_exp_repeatability`

- Status: `succeeded`
- Return code: `0`
- Runtime seconds: `39.6`
- Observed metric: `0.0`
- Failure category: `none`
- Command: `python scripts/run_minirocket_repeatability.py --dataset Coffee --runs 3 --output ./runs/minirocket_repeatability/metrics.json`
