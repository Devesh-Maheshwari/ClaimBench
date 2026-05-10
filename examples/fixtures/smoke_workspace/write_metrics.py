from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--accuracy", type=float, default=0.91)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"accuracy": args.accuracy, "runtime_seconds": 1.2}) + "\n",
        encoding="utf-8",
    )
    print(f"accuracy={args.accuracy}")


if __name__ == "__main__":
    main()
