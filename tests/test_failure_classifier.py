from __future__ import annotations

from claimbench.agents.failure_classifier import classify_failure, propose_repair


def test_classify_timeout() -> None:
    fc = classify_failure(status="timed_out", stderr="killed")
    assert fc.failure_type == "timeout"
    assert fc.retryable is True
    assert fc.route_to == "supervisor"


def test_classify_missing_dataset() -> None:
    fc = classify_failure(
        missing_files=["/tmp/data/UCR/Coffee/Coffee_TRAIN.tsv"],
        status="failed",
    )
    assert fc.failure_type == "missing_dataset"
    assert fc.route_to == "data_agent"


def test_classify_metric_parse() -> None:
    fc = classify_failure(error="MetricParseError: json path not found", returncode=0, status="failed")
    assert fc.failure_type == "metric_parse_failed"


def test_classify_claim_metric_mismatch() -> None:
    fc = classify_failure(
        returncode=0,
        status="failed",
        stdout="",
        stderr="",
        verdict_reason="Observed metric outside tolerance.",
    )
    assert fc.failure_type == "claim_metric_mismatch"
    assert fc.retryable is False


def test_classify_command_failed_nonzero() -> None:
    fc = classify_failure(returncode=1, stderr="command not found", status="failed")
    assert fc.failure_type == "command_failed"


def test_propose_repair_roundtrip() -> None:
    fc = classify_failure(returncode=137, stderr="Out Of Memory")
    proposal = propose_repair(fc)
    assert proposal["failure_type"] == "out_of_memory"
    assert "safety_note" in proposal
