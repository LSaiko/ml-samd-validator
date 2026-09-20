"""Pydantic v2 schemas for ml-samd-validator (FDA GMLP / PCCP for SaMD)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricName = Literal["sensitivity", "specificity", "auc", "f1", "calibration_slope"]
LOCKED_METRIC_NAMES: tuple[MetricName, ...] = (
    "sensitivity",
    "specificity",
    "auc",
    "f1",
    "calibration_slope",
)

# FDA GMLP 10 guiding principles, as short slugs.
GMLP_PRINCIPLES: tuple[str, ...] = (
    "multidisciplinary_expertise",
    "good_software_engineering",
    "representative_data",
    "independent_test_sets",
    "reference_standard",
    "design_fit_for_use",
    "human_ai_team_focus",
    "clinically_relevant_testing",
    "clear_user_information",
    "deployed_model_monitoring",
)


class RiskClass(StrEnum):
    """FDA SaMD risk categorization (IMDRF N12), I (lowest) to IV (highest)."""

    I = "I"  # noqa: E741 - FDA class numeral
    II = "II"
    III = "III"
    IV = "IV"


class ConfidenceBand(StrEnum):
    HIGH = "HIGH"
    AMBIGUOUS = "AMBIGUOUS"
    LOW = "LOW"


def band_for(confidence: float) -> ConfidenceBand:
    """Three-band routing: >=0.80 HIGH, 0.55-0.79 AMBIGUOUS, <0.55 LOW."""
    if confidence >= 0.80:
        return ConfidenceBand.HIGH
    if confidence >= 0.55:
        return ConfidenceBand.AMBIGUOUS
    return ConfidenceBand.LOW


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LockedMetrics(_Strict):
    sensitivity: float = Field(ge=0.0, le=1.0)
    specificity: float = Field(ge=0.0, le=1.0)
    auc: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    calibration_slope: float = Field(gt=0.0, le=10.0)


class ModelBaseline(_Strict):
    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    locked_metrics: LockedMetrics
    baseline_date: date
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    risk_classification: RiskClass
    sample_size: int = Field(gt=0)


class PerformanceBoundary(_Strict):
    metric: MetricName
    max_delta: float = Field(ge=0.0)


class ProposedChange(_Strict):
    model_id: str = Field(min_length=1)
    change_type: str = Field(min_length=1)
    description: str = ""
    expected_metric_deltas: dict[str, float] = Field(default_factory=dict)


class PredeterminedChangeControlPlan(_Strict):
    model_id: str = Field(min_length=1)
    authorized_change_types: list[str] = Field(min_length=1)
    performance_boundaries: list[PerformanceBoundary] = Field(default_factory=list)
    revalidation_triggers: list[str] = Field(default_factory=list)
    out_of_scope_changes: list[str] = Field(default_factory=list)

    def is_authorized(self, change_type: str) -> bool:
        return change_type.casefold() in {c.casefold() for c in self.authorized_change_types}

    def validate_change(self, change: ProposedChange) -> None:
        """Raise ValueError if the change type is not authorized by this PCCP."""
        if not self.is_authorized(change.change_type):
            raise ValueError(
                f"change_type {change.change_type!r} is not in authorized_change_types "
                f"{self.authorized_change_types}"
            )


class SubgroupMetrics(_Strict):
    subgroup: str = Field(min_length=1)
    metrics: dict[str, float]
    sample_size: int = Field(gt=0)


class PerformanceSnapshot(_Strict):
    model_id: str = Field(min_length=1)
    timestamp: datetime
    metrics: dict[str, float]
    subgroup_breakdown: list[SubgroupMetrics] = Field(default_factory=list)
    sample_size: int = Field(gt=0)
    drift_from_baseline: dict[str, float] | None = None

    def with_drift(self, baseline: ModelBaseline) -> PerformanceSnapshot:
        """Copy with drift = snapshot metric - baseline metric for each locked metric present."""
        locked = baseline.locked_metrics.model_dump()
        drift = {m: self.metrics[m] - locked[m] for m in LOCKED_METRIC_NAMES if m in self.metrics}
        return self.model_copy(update={"drift_from_baseline": drift})


class ModelCard(_Strict):
    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    intended_use: str
    training_data_summary: str
    performance_by_subgroup: list[SubgroupMetrics] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    pccp_reference: str
    gmlp_checklist: dict[str, bool]
    iec_62304_safety_class: Literal["A", "B", "C"]
    iso_14971_risk_controls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _gmlp_keys(self) -> ModelCard:
        unknown = set(self.gmlp_checklist) - set(GMLP_PRINCIPLES)
        if unknown:
            raise ValueError(f"unknown GMLP principle keys: {sorted(unknown)}")
        return self


# --- Phase 3: core-logic result models -------------------------------------------------


class MetricDrift(_Strict):
    metric: MetricName
    baseline_value: float
    snapshot_value: float
    delta: float
    p_value: float = Field(ge=0.0, le=1.0)
    verdict: Literal["stable", "drifted"]
    confidence: float = Field(ge=0.0, le=1.0)
    band: ConfidenceBand
    reasoning: str


class DriftReport(_Strict):
    model_id: str
    snapshot_timestamp: datetime
    metrics: list[MetricDrift]
    overall_band: ConfidenceBand
    requires_human_review: bool
    iec_62304_note: str
    iso_14971_note: str


PccpDecisionKind = Literal["pre-authorized", "requires new submission", "insufficient information"]


class PccpDecision(_Strict):
    model_id: str
    change_type: str
    decision: PccpDecisionKind
    rationale: str
    violated_boundaries: list[str] = Field(default_factory=list)
    confidence_band: ConfidenceBand


class SubgroupFinding(_Strict):
    subgroup: str
    metric: MetricName
    baseline_value: float
    subgroup_value: float
    delta: float
    verdict: Literal["stable", "drifted"]
    flagged: bool
    confidence: float = Field(ge=0.0, le=1.0)
    band: ConfidenceBand
    reasoning: str


class FairnessReport(_Strict):
    model_id: str
    threshold: float
    findings: list[SubgroupFinding]
    any_flagged: bool
    aggregate_passed: bool
    note: str = (
        "Subgroup flags may exist even when aggregate metrics pass; "
        "aggregate performance does not establish subgroup equity."
    )


# --- Phase 4: stable validation-evidence export (schema_version 1.0) -------------------


class Iec62304Classification(_Strict):
    safety_class: Literal["A", "B", "C"]
    rationale: str


class Iso14971Summary(_Strict):
    hazards: list[str]
    risk_controls: list[str]
    residual_risk_statement: str


class ValidationEvidence(_Strict):
    """Stable JSON export for traceability-matrix-dhf (docs/validation-evidence-schema.md)."""

    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    model_id: str
    version: str
    baseline: ModelBaseline
    snapshot: PerformanceSnapshot
    drift: DriftReport
    fairness: FairnessReport
    pccp_status: PccpDecision | None = None
    model_card: ModelCard | None = None
    iec_62304: Iec62304Classification
    iso_14971: Iso14971Summary
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    requirement_ids: list[str] = Field(default_factory=list)
