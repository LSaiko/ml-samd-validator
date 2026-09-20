from datetime import UTC, datetime

import pytest
from test_schemas import BASELINE, PCCP

from app.core import check_subgroups, detect_drift, evaluate_change
from schemas import ConfidenceBand, PerformanceSnapshot, ProposedChange, SubgroupMetrics

TS = datetime(2026, 3, 1, tzinfo=UTC)


def snap(metrics: dict[str, float], n: int = 500, **kw: object) -> PerformanceSnapshot:
    return PerformanceSnapshot(model_id="m1", timestamp=TS, metrics=metrics, sample_size=n, **kw)


# Baseline sensitivity 0.9 @ n=1000 vs snapshot n=500 (two-proportion z-test, verified numerically):
# delta -0.05 -> conf 0.996 HIGH; -0.018 -> 0.714 AMBIGUOUS; -0.005 -> 0.237 LOW.
@pytest.mark.parametrize(
    ("value", "band", "phrase"),
    [
        (0.85, ConfidenceBand.HIGH, "pass-through"),
        (0.882, ConfidenceBand.AMBIGUOUS, "flag for human interpretation"),
        (0.895, ConfidenceBand.LOW, "insufficient evidence, no conclusion asserted"),
    ],
)
def test_drift_bands(value: float, band: ConfidenceBand, phrase: str) -> None:
    report = detect_drift(BASELINE, snap({"sensitivity": value}))
    (m,) = report.metrics
    assert m.band is band and report.overall_band is band
    assert m.delta == pytest.approx(value - 0.9)
    assert m.confidence == pytest.approx(1 - m.p_value)
    assert phrase in m.reasoning.lower()
    assert report.requires_human_review is (band is not ConfidenceBand.HIGH)
    assert "IEC 62304 software safety class B" in report.iec_62304_note
    assert "ISO 14971" in report.iso_14971_note


def test_calibration_slope_uses_one_sample_approximation() -> None:
    report = detect_drift(BASELINE, snap({"calibration_slope": 1.15}))
    assert report.metrics[0].band is ConfidenceBand.HIGH


def test_overall_band_is_worst_and_pccp_boundary_forces_review() -> None:
    report = detect_drift(BASELINE, snap({"sensitivity": 0.85, "specificity": 0.845}))
    assert [m.band for m in report.metrics] == [ConfidenceBand.HIGH, ConfidenceBand.LOW]
    assert report.overall_band is ConfidenceBand.LOW
    # HIGH-confidence auc shift but |delta| 0.05 > PCCP max_delta 0.02 -> review
    report = detect_drift(BASELINE, snap({"auc": 0.98}), pccp=PCCP)
    assert report.overall_band is ConfidenceBand.HIGH and report.requires_human_review
    assert not detect_drift(BASELINE, snap({"auc": 0.98})).requires_human_review


def test_pccp_pre_authorized() -> None:
    change = ProposedChange(
        model_id="m1",
        change_type="retrain",
        description="Quarterly retrain on additional labelled studies.",
        expected_metric_deltas={"auc": 0.01},
    )
    d = evaluate_change(PCCP, change)
    assert d.decision == "pre-authorized" and d.violated_boundaries == []
    assert d.confidence_band is ConfidenceBand.HIGH


def test_pccp_requires_new_submission() -> None:
    base = dict(model_id="m1", description="Swap the backbone to a new ARCHITECTURE change.")
    out_of_scope = ProposedChange(
        **base, change_type="retrain", expected_metric_deltas={"auc": 0.0}
    )
    assert evaluate_change(PCCP, out_of_scope).decision == "requires new submission"
    unauthorized = ProposedChange(
        model_id="m1",
        change_type="prune",
        description="Prune 30% of weights.",
        expected_metric_deltas={"f1": 0},
    )
    assert "not in authorized_change_types" in evaluate_change(PCCP, unauthorized).rationale
    breach = ProposedChange(
        model_id="m1",
        change_type="retrain",
        description="Retrain expected to move AUC a lot.",
        expected_metric_deltas={"auc": -0.05},
    )
    d = evaluate_change(PCCP, breach)
    assert d.decision == "requires new submission" and d.violated_boundaries == [
        "auc: |-0.0500| > max_delta 0.02"
    ]


def test_pccp_insufficient_information() -> None:
    short = ProposedChange(
        model_id="m1", change_type="retrain", description="x", expected_metric_deltas={"auc": 0}
    )
    no_deltas = ProposedChange(
        model_id="m1", change_type="retrain", description="Long enough description here."
    )
    for c in (short, no_deltas):
        d = evaluate_change(PCCP, c)
        assert d.decision == "insufficient information" and d.confidence_band is ConfidenceBand.LOW


def test_subgroup_flag_while_aggregate_passes() -> None:
    s = snap(
        {"sensitivity": 0.89},
        subgroup_breakdown=[
            SubgroupMetrics(subgroup="age>65", metrics={"sensitivity": 0.84}, sample_size=120),
            SubgroupMetrics(subgroup="site_b", metrics={"sensitivity": 0.84}, sample_size=30),
            SubgroupMetrics(subgroup="female", metrics={"sensitivity": 0.90}, sample_size=200),
        ],
    )
    report = check_subgroups(BASELINE, s)
    assert report.aggregate_passed and report.any_flagged
    by = {f.subgroup: f for f in report.findings}
    assert by["age>65"].flagged and by["age>65"].band is ConfidenceBand.HIGH
    assert by["site_b"].flagged and by["site_b"].band is ConfidenceBand.AMBIGUOUS  # small n
    assert not by["female"].flagged and by["female"].band is ConfidenceBand.LOW
    assert "n=30" in by["site_b"].reasoning
    assert not check_subgroups(BASELINE, snap({"sensitivity": 0.8})).aggregate_passed
