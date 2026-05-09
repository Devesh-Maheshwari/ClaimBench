#!/usr/bin/env python
"""Run ROCKET on a single UCR dataset and write ClaimBench metrics JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from claimbench.runner.rocket_single_dataset import RocketRunError, run_rocket_single_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="UCR dataset name, e.g. Coffee.")
    parser.add_argument("--num-kernels", type=int, default=1000)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data/UCR"))
    parser.add_argument("--rocket-code-path", type=Path, default=Path("external/rocket/code"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        metrics = run_rocket_single_dataset(
            dataset=args.dataset,
            data_root=args.data_root,
            rocket_code_path=args.rocket_code_path,
            num_kernels=args.num_kernels,
            output_path=args.output,
        )
    except RocketRunError as exc:
        print(f"ROCKET run failed: {exc}")
        return 1

    print(f"accuracy={metrics['accuracy']}")
    print(f"runtime_seconds={metrics['runtime_seconds']}")
    print(f"metrics_path={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
