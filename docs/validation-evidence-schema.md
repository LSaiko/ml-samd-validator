# ValidationEvidence export schema (v1.0)

`ValidationEvidence` is the stable JSON contract emitted by `app.report.export_json` and
consumed by downstream tooling (notably `traceability-matrix-dhf`). The machine-readable
JSON Schema lives beside this file at `validation-evidence.schema.json` and is regenerated
with `python -m app.report`; `tests/test_report.py` fails if the two diverge.

All objects are `extra="forbid"`: unknown keys are rejected on ingest.

## Top level

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | `"1.0"` literal | Contract version (see versioning policy). |
| `generated_at` | ISO 8601 datetime (UTC) | When the Inspector produced this package. |
| `model_id` | string | Model identifier, copied from the baseline. |
| `version` | string | Model version, copied from the baseline. |
| `baseline` | `ModelBaseline` | The locked baseline the snapshot was judged against. |
| `snapshot` | `PerformanceSnapshot` | The evaluated snapshot with `drift_from_baseline` populated. |
| `drift` | `DriftReport` | Per-metric drift findings with three-band routing. |
| `fairness` | `FairnessReport` | Subgroup findings vs the baseline locked metrics. |
| `pccp_status` | `PccpDecision` or null | Present only when a `ProposedChange` was evaluated. |
| `model_card` | `ModelCard` or null | Manufacturer-supplied card content, if provided. |
| `iec_62304` | object | `safety_class` (A/B/C) and `rationale`. |
| `iso_14971` | object | `hazards`, `risk_controls`, `residual_risk_statement`. |
| `evidence_id` | UUID4 string | Unique id of this evidence package. |
| `requirement_ids` | list of strings | DHF requirement links; empty by default, filled by the DHF tool. |

## Nested objects

### `ModelBaseline`
`model_id`, `version`, `locked_metrics` (`sensitivity`, `specificity`, `auc`, `f1` in [0,1];
`calibration_slope` in (0,10]), `baseline_date` (ISO date), `dataset_hash` (64 hex chars),
`risk_classification` (`I`..`IV`, FDA SaMD/IMDRF), `sample_size` (>0).

### `PerformanceSnapshot`
`model_id`, `timestamp`, `metrics` (name -> value), `subgroup_breakdown` (list of
`SubgroupMetrics`: `subgroup`, `metrics`, `sample_size`), `sample_size`,
`drift_from_baseline` (locked metric -> snapshot minus baseline).

### `DriftReport`
| Field | Meaning |
|---|---|
| `model_id`, `snapshot_timestamp` | Identity of the comparison. |
| `metrics[]` | `MetricDrift`: `metric`, `baseline_value`, `snapshot_value`, `delta`, `p_value`, `verdict` (`stable` / `drifted` against the tolerance), `confidence` (in the verdict: `1 - p` if drifted, else the probability the true delta is within tolerance), `band`, `reasoning`. |
| `overall_band` | Worst band across metrics: LOW > AMBIGUOUS > HIGH. |
| `requires_human_review` | True when `overall_band != HIGH` or any metric's `verdict` is `drifted`. |
| `iec_62304_note` | Software safety class statement derived from `risk_classification`. |
| `iso_14971_note` | Fixed risk-control statement. |

`band` values: `HIGH` (confidence >= 0.80), `AMBIGUOUS` (0.55-0.79), `LOW` (< 0.55).

### `FairnessReport`
`model_id`, `threshold` (default 0.05), `findings[]` (`SubgroupFinding`: `subgroup`, `metric`,
`baseline_value`, `subgroup_value`, `delta`, `verdict`, `flagged` (= verdict `drifted`), `confidence`, `band`, `reasoning`),
`any_flagged`, `aggregate_passed`, `note`.

### `PccpDecision`
`model_id`, `change_type`, `decision` (`pre-authorized` | `requires new submission` |
`insufficient information`), `rationale`, `violated_boundaries[]`, `confidence_band`.

### `ModelCard`
`model_id`, `version`, `intended_use`, `training_data_summary`, `performance_by_subgroup[]`,
`known_limitations[]`, `pccp_reference`, `gmlp_checklist` (GMLP principle slug -> bool),
`iec_62304_safety_class`, `iso_14971_risk_controls[]`.

## Versioning policy

- `schema_version` follows `MAJOR.MINOR`. Adding an optional field is a MINOR bump;
  renaming, removing, retyping a field, or changing an enum/literal set is a MAJOR bump.
- Consumers must reject documents whose MAJOR differs from the one they were built against
  and may accept any MINOR at or below their own.
- `docs/validation-evidence.schema.json` is committed with every change and diffed in review.

## Ingestion by traceability-matrix-dhf

1. Validate the document against `validation-evidence.schema.json`; reject on failure.
2. Use `evidence_id` as the primary key of the evidence record (immutable, UUID4).
3. Link the record to design-history-file requirements by writing their ids into
   `requirement_ids`; the Inspector never populates this list itself.
4. Route by `drift.requires_human_review` and `fairness.any_flagged`: any `true` opens a
   review item; the evidence is never a go/no-go decision on its own.
5. Carry `iec_62304.safety_class` and `iso_14971.hazards` into the DHF risk file verbatim.
