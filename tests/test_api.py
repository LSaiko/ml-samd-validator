from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from test_schemas import BASELINE, PCCP

from app import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _reset() -> None:
    for store in (main.baselines, main.pccps, main.snapshots, main.decisions):
        store.clear()


def _snap(i: int, sens: float) -> dict:
    return {
        "model_id": "m1",
        "timestamp": datetime(2026, 3 + i, 1, tzinfo=UTC).isoformat(),
        "metrics": {"sensitivity": sens},
        "sample_size": 500,
        "subgroup_breakdown": [
            {"subgroup": "female", "metrics": {"sensitivity": sens - 0.06}, "sample_size": 200}
        ],
    }


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_404_without_baseline() -> None:
    assert client.get("/drift/m1").status_code == 404
    assert client.get("/model-card/m1").status_code == 404
    assert client.post("/snapshot", json=_snap(0, 0.9)).status_code == 404
    assert (
        client.post("/pccp/evaluate", json={"model_id": "m1", "change_type": "retrain"}).status_code
        == 404
    )


def test_full_flow() -> None:
    assert (
        client.post("/baseline", json=BASELINE.model_dump(mode="json")).json()["model_id"] == "m1"
    )
    assert client.post("/pccp", json=PCCP.model_dump(mode="json")).status_code == 200
    assert client.get("/model-card/m1").status_code == 404  # baseline but no snapshots yet
    # sensitivity 0.9 @ n=1000 vs n=500: -0.005 LOW, -0.018 AMBIGUOUS, -0.05 HIGH (see test_core)
    for i, sens in enumerate([0.895, 0.882, 0.85]):
        r = client.post("/snapshot", json=_snap(i, sens)).json()
        assert r["snapshot"]["drift_from_baseline"]["sensitivity"] == pytest.approx(sens - 0.9)
        assert {"drift", "fairness"} <= r.keys()
    drift = client.get("/drift/m1").json()
    assert [d["drift"]["overall_band"] for d in drift] == ["LOW", "AMBIGUOUS", "HIGH"]
    assert all(d["fairness"]["any_flagged"] for d in drift)

    change = {
        "model_id": "m1",
        "change_type": "retrain",
        "description": "Quarterly retrain on additional labelled studies.",
        "expected_metric_deltas": {"auc": 0.01},
    }
    assert client.post("/pccp/evaluate", json=change).json()["decision"] == "pre-authorized"
    assert len(client.get("/pccp/log/m1").json()) == 1

    card = client.get("/model-card/m1").json()
    assert card["schema_version"] == "1.0" and card["drift"]["overall_band"] == "HIGH"
    md = client.get("/model-card/m1", params={"format": "markdown"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert md.text.startswith("# Model Card: m1")
