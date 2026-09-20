from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel, ValidationError

from schemas import (
    GMLP_PRINCIPLES,
    ConfidenceBand,
    LockedMetrics,
    ModelBaseline,
    ModelCard,
    PerformanceBoundary,
    PerformanceSnapshot,
    PredeterminedChangeControlPlan,
    ProposedChange,
    RiskClass,
    SubgroupMetrics,
    band_for,
)

LOCKED = LockedMetrics(sensitivity=0.9, specificity=0.85, auc=0.93, f1=0.88, calibration_slope=1.0)
SUBGROUP = SubgroupMetrics(subgroup="age>65", metrics={"auc": 0.9}, sample_size=120)
BASELINE = ModelBaseline(
    model_id="m1",
    version="1.0.0",
    locked_metrics=LOCKED,
    baseline_date=date(2026, 1, 1),
    dataset_hash="a" * 64,
    risk_classification=RiskClass.II,
    sample_size=1000,
)
PCCP = PredeterminedChangeControlPlan(
    model_id="m1",
    authorized_change_types=["Retrain", "threshold_tune"],
    performance_boundaries=[PerformanceBoundary(metric="auc", max_delta=0.02)],
    revalidation_triggers=["auc drift > 0.02"],
    out_of_scope_changes=["architecture change"],
)
SNAPSHOT = PerformanceSnapshot(
    model_id="m1",
    timestamp=datetime(2026, 3, 1, tzinfo=UTC),
    metrics={"sensitivity": 0.88, "auc": 0.95, "extra": 0.5},
    subgroup_breakdown=[SUBGROUP],
    sample_size=500,
)
CARD = ModelCard(
    model_id="m1",
    version="1.0.0",
    intended_use="triage",
    training_data_summary="10k studies",
    performance_by_subgroup=[SUBGROUP],
    known_limitations=["pediatric"],
    pccp_reference="PCCP-001",
    gmlp_checklist=dict.fromkeys(GMLP_PRINCIPLES, True),
    iec_62304_safety_class="B",
    iso_14971_risk_controls=["human review"],
)
CHANGE = ProposedChange(model_id="m1", change_type="retrain", expected_metric_deltas={"auc": 0.01})


@pytest.mark.parametrize("obj", [LOCKED, SUBGROUP, BASELINE, PCCP, SNAPSHOT, CARD, CHANGE])
def test_round_trip(obj: BaseModel) -> None:
    assert type(obj).model_validate_json(obj.model_dump_json()) == obj


def test_pccp_rejects_unauthorized_change() -> None:
    with pytest.raises(ValueError):
        PCCP.validate_change(CHANGE.model_copy(update={"change_type": "architecture change"}))
    PCCP.validate_change(CHANGE)  # case-insensitive match passes


def test_with_drift() -> None:
    drifted = SNAPSHOT.with_drift(BASELINE)
    assert drifted.drift_from_baseline == pytest.approx({"sensitivity": -0.02, "auc": 0.02})
    assert SNAPSHOT.drift_from_baseline is None


def test_extra_forbidden_and_hash_pattern() -> None:
    with pytest.raises(ValidationError):
        LockedMetrics.model_validate({**LOCKED.model_dump(), "bogus": 1})
    with pytest.raises(ValidationError):
        ModelBaseline.model_validate({**BASELINE.model_dump(), "dataset_hash": "xyz"})


@pytest.mark.parametrize(
    ("c", "band"),
    [(0.8, ConfidenceBand.HIGH), (0.79, ConfidenceBand.AMBIGUOUS), (0.549, ConfidenceBand.LOW)],
)
def test_band_for(c: float, band: ConfidenceBand) -> None:
    assert band_for(c) is band
