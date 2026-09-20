"""Model card + validation-evidence generation (Markdown, PDF, stable JSON export)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core import (
    IEC_62304_CLASS,
    IEC_62304_RATIONALE,
    check_subgroups,
    detect_drift,
    evaluate_change,
)
from schemas import (
    GMLP_PRINCIPLES,
    ConfidenceBand,
    Iec62304Classification,
    Iso14971Summary,
    ModelBaseline,
    ModelCard,
    PerformanceSnapshot,
    PredeterminedChangeControlPlan,
    ProposedChange,
    ValidationEvidence,
)

DEFAULT_RISK_CONTROLS = [
    "Human review of every AMBIGUOUS/LOW-band or boundary-breaching finding before deployment.",
    "Locked baseline and dataset hash prevent silent re-baselining.",
    "PCCP boundaries gate which changes may ship without a new submission.",
]
RESIDUAL_RISK = (
    "Residual risk is accepted only after a qualified reviewer disposes each flagged finding; "
    "this evidence package asserts no autonomous go/no-go decision (ISO 14971 clause 7/8)."
)
DISCLAIMER = (
    "This document is validation evidence produced by the Inspector role. It flags deviations "
    "for human review under three-band confidence routing and does not constitute an autonomous "
    "go/no-go regulatory decision."
)


def build_model_card(
    baseline: ModelBaseline,
    snapshot: PerformanceSnapshot,
    pccp: PredeterminedChangeControlPlan | None = None,
    card: ModelCard | None = None,
    change: ProposedChange | None = None,
) -> ValidationEvidence:
    """Run all Inspector checks and package them as a ValidationEvidence export."""
    drift = detect_drift(baseline, snapshot, pccp)
    fairness = check_subgroups(baseline, snapshot)
    cls = IEC_62304_CLASS[baseline.risk_classification]
    hazards = [
        f"{m.metric} drift {m.delta:+.4f} ({m.band.value} confidence)"
        for m in drift.metrics
        if m.band is not ConfidenceBand.HIGH or m.delta < 0
    ] + [
        f"subgroup {f.subgroup}: {f.metric} delta {f.delta:+.4f}"
        for f in fairness.findings
        if f.flagged
    ]
    return ValidationEvidence(
        generated_at=datetime.now(UTC),
        model_id=baseline.model_id,
        version=baseline.version,
        baseline=baseline,
        snapshot=snapshot.with_drift(baseline),
        drift=drift,
        fairness=fairness,
        pccp_status=evaluate_change(pccp, change) if pccp and change else None,
        model_card=card,
        iec_62304=Iec62304Classification(
            safety_class=cls,
            rationale=IEC_62304_RATIONALE.format(cls=cls, risk=baseline.risk_classification.value),
        ),
        iso_14971=Iso14971Summary(
            hazards=hazards or ["No hazardous performance deviation observed in this snapshot."],
            risk_controls=card.iso_14971_risk_controls
            if card and card.iso_14971_risk_controls
            else DEFAULT_RISK_CONTROLS,
            residual_risk_statement=RESIDUAL_RISK,
        ),
    )


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)


def render_markdown(ev: ValidationEvidence) -> str:
    """GMLP-aligned model card in Markdown."""
    b, s, card = ev.baseline, ev.snapshot, ev.model_card
    locked = b.locked_metrics.model_dump()
    drift = {m.metric: m for m in ev.drift.metrics}
    pccp = ev.pccp_status
    checklist = card.gmlp_checklist if card else {}
    parts = [
        f"# Model Card: {ev.model_id} v{ev.version}",
        f"Evidence ID `{ev.evidence_id}` | schema {ev.schema_version} "
        f"| generated {ev.generated_at.isoformat()}",
        "## Intended Use",
        card.intended_use if card else "_Not supplied._",
        "## Training Data",
        card.training_data_summary if card else "_Not supplied._",
        "## Baseline vs Snapshot",
        _bullets(
            [
                f"Model: `{ev.model_id}` version `{ev.version}`",
                f"Baseline date: {b.baseline_date.isoformat()} (n={b.sample_size}), "
                f"dataset hash `{b.dataset_hash}`",
                f"Snapshot: {s.timestamp.isoformat()} (n={s.sample_size})",
                f"FDA SaMD risk class: {b.risk_classification.value}",
            ]
        ),
        _table(
            ["Metric", "Baseline", "Snapshot", "Delta", "p-value", "Band"],
            [
                [
                    m,
                    f"{locked[m]:.4f}",
                    f"{d.snapshot_value:.4f}",
                    f"{d.delta:+.4f}",
                    f"{d.p_value:.3g}",
                    d.band.value,
                ]
                for m, d in drift.items()
            ],
        ),
        "## Drift Findings",
        f"Overall band: **{ev.drift.overall_band.value}** "
        f"| requires human review: **{ev.drift.requires_human_review}**",
        _bullets([d.reasoning for d in ev.drift.metrics])
        or "_No locked metrics present in snapshot._",
        "## Subgroup Fairness",
        f"Threshold |delta| > {ev.fairness.threshold} | any flagged: **{ev.fairness.any_flagged}** "
        f"| aggregate passed: **{ev.fairness.aggregate_passed}**",
        _table(
            ["Subgroup", "Metric", "Baseline", "Subgroup", "Delta", "Flagged", "Band"],
            [
                [
                    f.subgroup,
                    f.metric,
                    f"{f.baseline_value:.4f}",
                    f"{f.subgroup_value:.4f}",
                    f"{f.delta:+.4f}",
                    str(f.flagged),
                    f.band.value,
                ]
                for f in ev.fairness.findings
            ],
        ),
        f"_{ev.fairness.note}_",
        "## PCCP Status",
        (
            f"Change `{pccp.change_type}`: **{pccp.decision}** "
            f"({pccp.confidence_band.value}). {pccp.rationale}"
            + (("\n" + _bullets(pccp.violated_boundaries)) if pccp.violated_boundaries else "")
            if pccp
            else "_No proposed change evaluated._"
            + (f" PCCP reference: {card.pccp_reference}" if card else "")
        ),
        "## GMLP Checklist",
        _bullets([f"[{'x' if checklist.get(p) else ' '}] {p}" for p in GMLP_PRINCIPLES]),
        "## IEC 62304 Software Safety Classification",
        f"**Class {ev.iec_62304.safety_class}.** {ev.iec_62304.rationale}",
        "## ISO 14971 Risk Management",
        "\n".join(f"> **Hazard:** {h}" for h in ev.iso_14971.hazards),
        "\n".join(f"> **Risk control:** {c}" for c in ev.iso_14971.risk_controls),
        f"> **Residual risk:** {ev.iso_14971.residual_risk_statement}",
        "## Known Limitations",
        _bullets(card.known_limitations) if card and card.known_limitations else "_None recorded._",
        "## Inspector Disclaimer",
        DISCLAIMER,
    ]
    return "\n\n".join(parts) + "\n"


def render_pdf(ev: ValidationEvidence, out: Path) -> Path:
    """Render the Markdown model card into a simple reportlab PDF (headings, paragraphs, tables)."""
    styles = getSampleStyleSheet()
    story: list[object] = []
    grid = TableStyle(
        [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ]
    )
    for block in render_markdown(ev).split("\n\n"):
        if block.startswith("|"):
            rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in block.splitlines()]
            story.append(Table([rows[0], *rows[2:]], style=grid, hAlign="LEFT"))
        elif block.startswith("#"):
            level = len(block) - len(block.lstrip("#"))
            story.append(Paragraph(escape(block.lstrip("# ")), styles[f"Heading{min(level, 3)}"]))
        else:
            story.append(Paragraph(escape(block).replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 6))
    out.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out), title=f"Model Card {ev.model_id} v{ev.version}").build(story)
    return out


def export_json(ev: ValidationEvidence, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ev.model_dump_json(indent=2), encoding="utf-8")
    return out


__all__ = ["build_model_card", "export_json", "render_markdown", "render_pdf"]


if __name__ == "__main__":  # python -m app.report -> refresh docs/validation-evidence.schema.json
    import json

    target = Path(__file__).resolve().parents[1] / "docs" / "validation-evidence.schema.json"
    target.write_text(
        json.dumps(ValidationEvidence.model_json_schema(), indent=2) + "\n", encoding="utf-8"
    )
    print(target)
