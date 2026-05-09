"""Metric parsing utilities for experiment outputs."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


class MetricParseError(Exception):
    """Raised when a metric cannot be parsed from experiment output."""


def parse_metric(parser: dict[str, str], *, stdout: str, output_path: Path | None = None) -> Any:
    """Parse a metric using the parser contract from a manifest experiment."""

    parser_type = parser["type"]
    target = parser["target"]

    if parser_type == "regex":
        return _parse_regex(stdout, target)
    if parser_type == "json_path":
        if output_path is None:
            raise MetricParseError("json_path parser requires an output path")
        return _parse_json_path(output_path, target)
    if parser_type == "csv_column":
        if output_path is None:
            raise MetricParseError("csv_column parser requires an output path")
        return _parse_csv_column(output_path, target)
    if parser_type == "custom":
        raise MetricParseError("custom metric parsers are not implemented yet")

    raise MetricParseError(f"Unsupported metric parser type: {parser_type}")


def _parse_regex(stdout: str, pattern: str) -> str:
    match = re.search(pattern, stdout)
    if not match:
        raise MetricParseError(f"Regex did not match stdout: {pattern}")
    if match.groups():
        return match.group(1)
    return match.group(0)


def _parse_json_path(path: Path, target: str) -> Any:
    if not target.startswith("$."):
        raise MetricParseError(f"Only simple $.key JSON paths are supported: {target}")

    data = json.loads(path.read_text(encoding="utf-8"))
    current: Any = data
    for part in target[2:].split("."):
        if not isinstance(current, dict) or part not in current:
            raise MetricParseError(f"JSON path not found: {target}")
        current = current[part]
    return current


def _parse_csv_column(path: Path, column: str) -> Any:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise MetricParseError(f"CSV file has no data rows: {path}")
    if column not in rows[0]:
        raise MetricParseError(f"CSV column not found: {column}")
    return rows[-1][column]
