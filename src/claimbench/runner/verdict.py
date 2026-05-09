"""Claim verdict calculation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClaimVerdict:
    """Result of comparing observed and expected claim metrics."""

    status: str
    expected: Any
    observed: Any
    tolerance: dict[str, Any]
    reason: str


def compute_verdict(claim: dict[str, Any], observed: Any) -> ClaimVerdict:
    """Compare an observed metric against a claim expectation."""

    expected = claim["expected_metric"]["value"]
    tolerance = claim["tolerance"]
    tolerance_type = tolerance["type"]

    if expected == "to_be_measured":
        return ClaimVerdict(
            status="needs_review",
            expected=expected,
            observed=observed,
            tolerance=tolerance,
            reason="Expected value is not locked yet.",
        )

    if tolerance_type == "exact":
        reproduced = observed == expected
        return _verdict(reproduced, expected, observed, tolerance)

    if tolerance_type in {"absolute", "relative"}:
        expected_float = _to_float(expected)
        observed_float = _to_float(observed)
        tolerance_float = _to_float(tolerance["value"])
        if tolerance_type == "absolute":
            reproduced = abs(observed_float - expected_float) <= tolerance_float
        else:
            reproduced = abs(observed_float - expected_float) <= abs(expected_float) * tolerance_float
        return _verdict(reproduced, expected, observed, tolerance)

    return ClaimVerdict(
        status="needs_review",
        expected=expected,
        observed=observed,
        tolerance=tolerance,
        reason="Manual tolerance requires human review.",
    )


def _verdict(
    reproduced: bool,
    expected: Any,
    observed: Any,
    tolerance: dict[str, Any],
) -> ClaimVerdict:
    return ClaimVerdict(
        status="reproduced" if reproduced else "failed",
        expected=expected,
        observed=observed,
        tolerance=tolerance,
        reason="Observed metric is within tolerance."
        if reproduced
        else "Observed metric is outside tolerance.",
    )


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected numeric value, got {value!r}") from exc
