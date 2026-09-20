import json
from pathlib import Path

from test_schemas import BASELINE, CARD, CHANGE, PCCP, SNAPSHOT

from app.report import build_model_card, export_json, render_markdown, render_pdf
from schemas import ValidationEvidence

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "docs" / "validation-evidence.schema.json"
EV = build_model_card(BASELINE, SNAPSHOT, PCCP, CARD, CHANGE)


def test_markdown_cites_identifiers() -> None:
    md = render_markdown(EV)
    for needle in (
        "`m1`",
        "`1.0.0`",
        SNAPSHOT.timestamp.isoformat(),
        BASELINE.dataset_hash,
        "IEC 62304",
        "> **Hazard:**",
        "insufficient information",  # CHANGE fixture has no description
        "human review",
    ):
        assert needle in md
    assert render_markdown(build_model_card(BASELINE, SNAPSHOT)).count("_Not supplied._") == 2


def test_pdf_written(tmp_path: Path) -> None:
    out = render_pdf(EV, tmp_path / "card.pdf")
    assert out.exists() and out.stat().st_size > 1024


def test_json_round_trip(tmp_path: Path) -> None:
    out = export_json(EV, tmp_path / "evidence.json")
    assert ValidationEvidence.model_validate_json(out.read_text(encoding="utf-8")) == EV
    assert EV.schema_version == "1.0" and len(EV.evidence_id) == 36 and EV.requirement_ids == []


def test_json_schema_file_matches_model() -> None:
    """Regenerate with: python -m app.report (writes docs/validation-evidence.schema.json)."""
    assert (
        json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        == ValidationEvidence.model_json_schema()
    )
