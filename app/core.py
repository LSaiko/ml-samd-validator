"""Inspector core logic: drift detection, PCCP evaluation, subgroup fairness.

Statistical test choice: a PerformanceSnapshot carries metric-level summary statistics
(sensitivity, AUC, ...) and a sample size, not raw prediction-score distributions, so
distribution-shift measures such as PSI/KL are not applicable. Each proportion-like metric
is instead compared with a two-proportion z-test (pooled SE) between baseline and snapshot
cohorts; confidence = 1 - p_value is then routed through the three bands in ``band_for``.
"""

from __future__ import annotations

import math

from scipy.stats import norm

from schemas import (
    LOCKED_METRIC_NAMES,
    ConfidenceBand,
    DriftReport,
    FairnessReport,
    MetricDrift,
    ModelBaseline,
    PccpDecision,
    PerformanceSnapshot,
    PredeterminedChangeControlPlan,
    ProposedChange,
    RiskClass,
    SubgroupFinding,
    band_for,
)

IEC_62304_CLASS: dict[RiskClass, str] = {
    RiskClass.I: "A",
    RiskClass.II: "B",
    RiskClass.III: "C",
    RiskClass.IV: "C",
}
IEC_62304_RATIONALE = (
    "IEC 62304 software safety class {cls} assigned from FDA SaMD risk class {risk}: "
    "class A = no injury possible, B = non-serious injury possible, C = death or serious "
    "injury possible. Classification is provisional pending hazard analysis by the manufacturer."
)
ISO_14971_NOTE = (
    "ISO 14971: observed performance deviations are treated as hazardous situations. "
    "The risk control is human review of every flagged deviation before any deployment "
    "decision; this report is evidence, not a release decision."
)
MIN_DESCRIPTION_CHARS = 20


def p_value(metric: str, p1: float, n1: int, p2: float, n2: int) -> float:
    """Two-sided p-value for baseline (p1, n1) vs comparison (p2, n2) on ``metric``."""
    if metric == "calibration_slope":
        # ponytail: slope has no closed-form SE without raw data; approximate SE = 1/sqrt(n2).
        se = 1.0 / math.sqrt(n2)
    else:
        pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
        se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (p2 - p1) / se
    return float(2 * norm.sf(abs(z)))


def _reasoning(metric: str, delta: float, confidence: float, band: ConfidenceBand) -> str:
    base = f"{metric} delta {delta:+.4f}, confidence {confidence:.2f} ({band.value})."
    if band is ConfidenceBand.HIGH:
        return f"{base} Statistically supported shift; pass-through."
    if band is ConfidenceBand.AMBIGUOUS:
        return f"{base} Flag for human interpretation: sample sizes give only moderate power."
    return f"{base} Insufficient evidence, no conclusion asserted."


def _worst(bands: list[ConfidenceBand]) -> ConfidenceBand:
    if ConfidenceBand.LOW in bands:
        return ConfidenceBand.LOW
    if ConfidenceBand.AMBIGUOUS in bands:
        return ConfidenceBand.AMBIGUOUS
    return ConfidenceBand.HIGH


def _boundaries(pccp: PredeterminedChangeControlPlan | None) -> dict[str, float]:
    return {b.metric: b.max_delta for b in pccp.performance_boundaries} if pccp else {}


def detect_drift(
    baseline: ModelBaseline,
    snapshot: PerformanceSnapshot,
    pccp: PredeterminedChangeControlPlan | None = None,
) -> DriftReport:
    """Compare each locked metric present in the snapshot to the baseline (see module doc)."""
    locked = baseline.locked_metrics.model_dump()
    findings: list[MetricDrift] = []
    for metric in LOCKED_METRIC_NAMES:
        if metric not in snapshot.metrics:
            continue
        b, s = locked[metric], snapshot.metrics[metric]
        p = p_value(metric, b, baseline.sample_size, s, snapshot.sample_size)
        conf = 1 - p
        band = band_for(conf)
        findings.append(
            MetricDrift(
                metric=metric,
                baseline_value=b,
                snapshot_value=s,
                delta=s - b,
                p_value=p,
                confidence=conf,
                band=band,
                reasoning=_reasoning(metric, s - b, conf, band),
            )
        )
    overall = _worst([f.band for f in findings])
    limits = _boundaries(pccp)
    breached = any(abs(f.delta) > limits[f.metric] for f in findings if f.metric in limits)
    cls = IEC_62304_CLASS[baseline.risk_classification]
    return DriftReport(
        model_id=baseline.model_id,
        snapshot_timestamp=snapshot.timestamp,
        metrics=findings,
        overall_band=overall,
        requires_human_review=overall is not ConfidenceBand.HIGH or breached,
        iec_62304_note=IEC_62304_RATIONALE.format(cls=cls, risk=baseline.risk_classification.value),
        iso_14971_note=ISO_14971_NOTE,
    )


def evaluate_change(pccp: PredeterminedChangeControlPlan, change: ProposedChange) -> PccpDecision:
    """Route a proposed change against the PCCP: pre-authorized / new submission / insufficient."""
    common = {"model_id": change.model_id, "change_type": change.change_type}
    if len(change.description.strip()) < MIN_DESCRIPTION_CHARS or not change.expected_metric_deltas:
        return PccpDecision(
            **common,
            decision="insufficient information",
            rationale="Description under 20 characters or no expected metric deltas supplied.",
            confidence_band=ConfidenceBand.LOW,
        )
    text = f"{change.change_type} {change.description}".casefold()
    scope_hits = [o for o in pccp.out_of_scope_changes if o.casefold() in text]
    limits = _boundaries(pccp)
    violated = [
        f"{m}: |{d:+.4f}| > max_delta {limits[m]}"
        for m, d in change.expected_metric_deltas.items()
        if m in limits and abs(d) > limits[m]
    ]
    reasons: list[str] = []
    if not pccp.is_authorized(change.change_type):
        reasons.append(f"change_type {change.change_type!r} not in authorized_change_types")
    if scope_hits:
        reasons.append(f"matches out_of_scope_changes {scope_hits}")
    if violated:
        reasons.append("expected deltas exceed performance boundaries")
    if reasons:
        return PccpDecision(
            **common,
            decision="requires new submission",
            rationale="; ".join(reasons) + ".",
            violated_boundaries=violated,
            confidence_band=ConfidenceBand.HIGH,
        )
    return PccpDecision(
        **common,
        decision="pre-authorized",
        rationale="Change type authorized, not out of scope, expected deltas within boundaries.",
        confidence_band=ConfidenceBand.HIGH,
    )


def check_subgroups(
    baseline: ModelBaseline, snapshot: PerformanceSnapshot, threshold: float = 0.05
) -> FairnessReport:
    """Flag any subgroup whose locked metric deviates from baseline by more than ``threshold``."""
    locked = baseline.locked_metrics.model_dump()
    findings: list[SubgroupFinding] = []
    for sg in snapshot.subgroup_breakdown:
        for metric in LOCKED_METRIC_NAMES:
            if metric not in sg.metrics:
                continue
            b, v = locked[metric], sg.metrics[metric]
            p = p_value(metric, b, baseline.sample_size, v, sg.sample_size)
            conf = 1 - p
            band = band_for(conf)
            findings.append(
                SubgroupFinding(
                    subgroup=sg.subgroup,
                    metric=metric,
                    baseline_value=b,
                    subgroup_value=v,
                    delta=v - b,
                    flagged=abs(v - b) > threshold,
                    confidence=conf,
                    band=band,
                    reasoning=f"[{sg.subgroup}, n={sg.sample_size}] "
                    + _reasoning(metric, v - b, conf, band),
                )
            )
    aggregate_passed = all(
        abs(snapshot.metrics[m] - locked[m]) <= threshold
        for m in LOCKED_METRIC_NAMES
        if m in snapshot.metrics
    )
    return FairnessReport(
        model_id=baseline.model_id,
        threshold=threshold,
        findings=findings,
        any_flagged=any(f.flagged for f in findings),
        aggregate_passed=aggregate_passed,
    )


__all__ = ["check_subgroups", "detect_drift", "evaluate_change", "p_value"]
