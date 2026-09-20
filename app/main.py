"""FastAPI surface for the Inspector: baseline, PCCP, snapshots, drift, model card."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.core import check_subgroups, detect_drift, evaluate_change
from app.report import build_model_card, render_markdown
from schemas import (
    ModelBaseline,
    PccpDecision,
    PerformanceSnapshot,
    PredeterminedChangeControlPlan,
    ProposedChange,
    ValidationEvidence,
)

app = FastAPI(title="ml-samd-validator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ponytail: in-memory store, swap for sqlite if persistence needed
baselines: dict[str, ModelBaseline] = {}
pccps: dict[str, PredeterminedChangeControlPlan] = {}
snapshots: defaultdict[str, list[PerformanceSnapshot]] = defaultdict(list)
decisions: defaultdict[str, list[PccpDecision]] = defaultdict(list)


def _baseline(model_id: str) -> ModelBaseline:
    if model_id not in baselines:
        raise HTTPException(404, f"no baseline for model_id {model_id!r}")
    return baselines[model_id]


def _analyse(snapshot: PerformanceSnapshot) -> dict[str, Any]:
    b = _baseline(snapshot.model_id)
    return {
        "snapshot_timestamp": snapshot.timestamp,
        "drift": detect_drift(b, snapshot, pccps.get(snapshot.model_id)),
        "fairness": check_subgroups(b, snapshot),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/baseline")
def post_baseline(baseline: ModelBaseline) -> ModelBaseline:
    baselines[baseline.model_id] = baseline
    return baseline


@app.post("/pccp")
def post_pccp(pccp: PredeterminedChangeControlPlan) -> PredeterminedChangeControlPlan:
    pccps[pccp.model_id] = pccp
    return pccp


@app.post("/snapshot")
def post_snapshot(snapshot: PerformanceSnapshot) -> dict[str, Any]:
    snapshot = snapshot.with_drift(_baseline(snapshot.model_id))
    snapshots[snapshot.model_id].append(snapshot)
    return {"snapshot": snapshot, **_analyse(snapshot)}


@app.get("/drift/{model_id}")
def get_drift(model_id: str) -> list[dict[str, Any]]:
    _baseline(model_id)
    return [_analyse(s) for s in sorted(snapshots[model_id], key=lambda s: s.timestamp)]


@app.post("/pccp/evaluate")
def post_evaluate(change: ProposedChange) -> PccpDecision:
    if change.model_id not in pccps:
        raise HTTPException(404, f"no PCCP for model_id {change.model_id!r}")
    decision = evaluate_change(pccps[change.model_id], change)
    decisions[change.model_id].append(decision)
    return decision


@app.get("/pccp/log/{model_id}")
def get_log(model_id: str) -> list[PccpDecision]:
    return decisions[model_id]


@app.get("/model-card/{model_id}", response_model=None)
def get_model_card(model_id: str, format: str = "json") -> ValidationEvidence | PlainTextResponse:
    b = _baseline(model_id)
    if not snapshots[model_id]:
        raise HTTPException(404, f"no snapshots for model_id {model_id!r}")
    latest = max(snapshots[model_id], key=lambda s: s.timestamp)
    ev = build_model_card(b, latest, pccps.get(model_id))
    if format == "markdown":
        return PlainTextResponse(render_markdown(ev), media_type="text/markdown")
    return ev
