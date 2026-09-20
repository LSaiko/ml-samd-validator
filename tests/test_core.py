from datetime import UTC, datetime

import pytest
from test_schemas import BASELINE, PCCP

from app.core import check_subgroups, detect_drift, evaluate_change, p_value, verdict_confidence
from schemas import (
    ConfidenceBand,
    PerformanceBoundary,
    PerformanceSnapshot,
    PredeterminedChangeControlPlan,
    ProposedChange,
    SubgroupMetrics,
)

TS = datetime(2026, 3, 1, tzinfo=UTC)


def snap(metrics: dict[str, float], n: int = 500, **kw: object) -> PerformanceSnapshot:
    return PerformanceSnapshot(model_id="m1", timestamp=TS, metrics=metrics, sample_size=n, **kw)


# Baseline sensitivity 0.9 @ n=1000, default tolerance 0.02 (verified numerically):
# stable (delta 0): n=2000 -> P(|true delta|<=tol) 0.915 HIGH; n=300 -> 0.689 AMBIGUOUS;
#   n=50 -> 0.355 LOW.
# drifted (1-p): 0.85@500 -> 0.996 HIGH; 0.87@100 -> 0.654 AMBIGUOUS; 0.875@50 -> 0.433 LOW.
@pytest.mark.parametrize(
    ("value", "n", "verdict", "conf", "band", "phrase"),
    [
        (0.9, 2000, "stable", 0.915, ConfidenceBand.HIGH, "within tolerance ±0.02"),
        (0.9, 300, "stable", 0.689, ConfidenceBand.AMBIGUOUS, "verdict 'stable'"),
        (0.9, 50, "stable", 0.355, ConfidenceBand.LOW, "no conclusion asserted"),
        (0.85, 500, "drifted", 0.996, ConfidenceBand.HIGH, "drift beyond tolerance"),
        (0.87, 100, "drifted", 0.654, ConfidenceBand.AMBIGUOUS, "verdict 'drifted'"),
        (0.875, 50, "drifted", 0.433, ConfidenceBand.LOW, "no conclusion asserted"),
    ],
)
def test_drift_bands(
    value: float, n: int, verdict: str, conf: float, band: ConfidenceBand, phrase: str
) -> None:
    report = detect_drift(BASELINE, snap({"sensitivity": value}, n))
    (m,) = report.metrics
    assert m.verdict == verdict and m.band is band and report.overall_band is band
    assert m.delta == pytest.approx(value - 0.9)
    assert m.confidence == pytest.approx(conf, abs=5e-4)
    if verdict == "drifted":
        assert m.confidence == pytest.approx(1 - m.p_value)
    assert phrase in m.reasoning.lower()
    # only a HIGH-confidence *stable* verdict is a pass-through
    assert report.requires_human_review is not (band is ConfidenceBand.HIGH and verdict == "stable")
    assert "IEC 62304 software safety class B" in report.iec_62304_note
    assert "ISO 14971" in report.iso_14971_note


def test_degenerate_proportion_has_zero_se() -> None:
    assert p_value("sensitivity", 1.0, 100, 1.0, 100) == 1.0
    assert verdict_confidence("sensitivity", 1.0, 100, 1.0, 100, 0.02) == ("stable", 1.0, 1.0)


def test_calibration_slope_uses_one_sample_approximation() -> None:
    report = detect_drift(BASELINE, snap({"calibration_slope": 1.15}))
    assert report.metrics[0].band is ConfidenceBand.HIGH


def test_overall_band_is_worst_and_pccp_sets_tolerance() -> None:
    # sensitivity 0.85 drifted HIGH (0.996); specificity 0.845 stable AMBIGUOUS (0.676)
    report = detect_drift(BASELINE, snap({"sensitivity": 0.85, "specificity": 0.845}))
    assert [m.band for m in report.metrics] == [ConfidenceBand.HIGH, ConfidenceBand.AMBIGUOUS]
    assert report.overall_band is ConfidenceBand.AMBIGUOUS
    # auc +0.015 @ n=500: within default 0.02 (stable, 0.640) but beyond a PCCP max_delta 0.01
    # (drifted, 0.733); the verdict, not the band, decides review.
    tight = PredeterminedChangeControlPlan(
        model_id="m1",
        authorized_change_types=["retrain"],
        performance_boundaries=[PerformanceBoundary(metric="auc", max_delta=0.01)],
    )
    loose, strict = (detect_drift(BASELINE, snap({"auc": 0.945}), pccp=p) for p in (None, tight))
    assert (loose.metrics[0].verdict, strict.metrics[0].verdict) == ("stable", "drifted")
    assert loose.overall_band is strict.overall_band is ConfidenceBand.AMBIGUOUS
    assert loose.requires_human_review and strict.requires_human_review


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
    # threshold 0.05 is the tolerance: 0.84@120 drifted 0.956 HIGH; 0.84@30 drifted 0.716
    # AMBIGUOUS (small n); 0.90@200 stable 0.969 HIGH (unflagged, pass-through).
    assert by["age>65"].flagged and by["age>65"].band is ConfidenceBand.HIGH
    assert by["site_b"].flagged and by["site_b"].band is ConfidenceBand.AMBIGUOUS  # small n
    assert not by["female"].flagged and by["female"].band is ConfidenceBand.HIGH
    assert by["female"].verdict == "stable" and "pass-through" in by["female"].reasoning
    assert "n=30" in by["site_b"].reasoning
    assert not check_subgroups(BASELINE, snap({"sensitivity": 0.8})).aggregate_passed
