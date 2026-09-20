// Synthetic seed shown when VITE_API_BASE is unset (GitHub Pages). Shapes match the API responses.
import type { Baseline, DriftEntry, PccpDecision } from "./types";

export const seedBaseline: Baseline = { model_id: "cxr-pneumothorax", version: "1.0.0", risk_classification: "II" };

// Gradual-drift story, HIGH (stable) -> AMBIGUOUS -> LOW -> HIGH (drifted). Values computed with
// app.core.verdict_confidence: baseline n=2000 (sens 0.90, spec 0.88, auc 0.94), snapshot n =
// 1500/600/800/1200, tolerance 0.02 per metric and 0.05 per subgroup (the fairness threshold).
export const seedDrift: DriftEntry[] = [
  {
    snapshot_timestamp: "2026-03-01T00:00:00Z",
    drift: { overall_band: "HIGH", requires_human_review: false, metrics: [
      { metric: "sensitivity", delta: -0.003, verdict: "stable", confidence: 0.938, band: "HIGH" },
      { metric: "specificity", delta: 0.002, verdict: "stable", confidence: 0.925, band: "HIGH" },
      { metric: "auc", delta: -0.002, verdict: "stable", confidence: 0.983, band: "HIGH" },
    ] },
    fairness: { any_flagged: false, findings: [
      { subgroup: "female", metric: "sensitivity", delta: -0.0048, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "female", metric: "specificity", delta: 0.0032, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "female", metric: "auc", delta: -0.0032, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "sensitivity", delta: -0.0021, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "specificity", delta: 0.0014, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "auc", delta: -0.0014, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "sensitivity", delta: -0.0039, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "specificity", delta: 0.0026, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "auc", delta: -0.0026, verdict: "stable", flagged: false, band: "HIGH" },
    ] },
  },
  {
    snapshot_timestamp: "2026-04-01T00:00:00Z",
    drift: { overall_band: "AMBIGUOUS", requires_human_review: true, metrics: [
      { metric: "sensitivity", delta: -0.012, verdict: "stable", confidence: 0.703, band: "AMBIGUOUS" },
      { metric: "specificity", delta: -0.006, verdict: "stable", confidence: 0.778, band: "AMBIGUOUS" },
      { metric: "auc", delta: -0.008, verdict: "stable", confidence: 0.851, band: "HIGH" },
    ] },
    fairness: { any_flagged: false, findings: [
      { subgroup: "female", metric: "sensitivity", delta: -0.0192, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "female", metric: "specificity", delta: -0.0096, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "female", metric: "auc", delta: -0.0128, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "sensitivity", delta: -0.0084, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "specificity", delta: -0.0042, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "auc", delta: -0.0056, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "sensitivity", delta: -0.0156, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "specificity", delta: -0.0078, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "auc", delta: -0.0104, verdict: "stable", flagged: false, band: "HIGH" },
    ] },
  },
  {
    snapshot_timestamp: "2026-05-01T00:00:00Z",
    drift: { overall_band: "LOW", requires_human_review: true, metrics: [
      { metric: "sensitivity", delta: -0.031, verdict: "drifted", confidence: 0.983, band: "HIGH" },
      { metric: "specificity", delta: -0.014, verdict: "stable", confidence: 0.661, band: "AMBIGUOUS" },
      { metric: "auc", delta: -0.019, verdict: "stable", confidence: 0.538, band: "LOW" },
    ] },
    fairness: { any_flagged: false, findings: [
      { subgroup: "female", metric: "sensitivity", delta: -0.0496, verdict: "stable", flagged: false, band: "LOW" },
      { subgroup: "female", metric: "specificity", delta: -0.0224, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "female", metric: "auc", delta: -0.0304, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "sensitivity", delta: -0.0217, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "specificity", delta: -0.0098, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "auc", delta: -0.0133, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "sensitivity", delta: -0.0403, verdict: "stable", flagged: false, band: "AMBIGUOUS" },
      { subgroup: "age>=65", metric: "specificity", delta: -0.0182, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "auc", delta: -0.0247, verdict: "stable", flagged: false, band: "HIGH" },
    ] },
  },
  {
    snapshot_timestamp: "2026-06-01T00:00:00Z",
    drift: { overall_band: "HIGH", requires_human_review: true, metrics: [
      { metric: "sensitivity", delta: -0.052, verdict: "drifted", confidence: 1.0, band: "HIGH" },
      { metric: "specificity", delta: -0.027, verdict: "drifted", confidence: 0.972, band: "HIGH" },
      { metric: "auc", delta: -0.035, verdict: "drifted", confidence: 1.0, band: "HIGH" },
    ] },
    fairness: { any_flagged: true, findings: [
      { subgroup: "female", metric: "sensitivity", delta: -0.0832, verdict: "drifted", flagged: true, band: "HIGH" },
      { subgroup: "female", metric: "specificity", delta: -0.0432, verdict: "stable", flagged: false, band: "AMBIGUOUS" },
      { subgroup: "female", metric: "auc", delta: -0.056, verdict: "drifted", flagged: true, band: "HIGH" },
      { subgroup: "male", metric: "sensitivity", delta: -0.0364, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "specificity", delta: -0.0189, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "male", metric: "auc", delta: -0.0245, verdict: "stable", flagged: false, band: "HIGH" },
      { subgroup: "age>=65", metric: "sensitivity", delta: -0.0676, verdict: "drifted", flagged: true, band: "HIGH" },
      { subgroup: "age>=65", metric: "specificity", delta: -0.0351, verdict: "stable", flagged: false, band: "AMBIGUOUS" },
      { subgroup: "age>=65", metric: "auc", delta: -0.0455, verdict: "stable", flagged: false, band: "AMBIGUOUS" },
    ] },
  },
];

export const seedLog: PccpDecision[] = [
  {
    change_type: "retrain",
    decision: "pre-authorized",
    rationale: "Change type authorized, not out of scope, expected deltas within boundaries.",
    confidence_band: "HIGH",
  },
  {
    change_type: "retrain",
    decision: "requires new submission",
    rationale: "matches out_of_scope_changes ['architecture change']; expected deltas exceed performance boundaries.",
    confidence_band: "HIGH",
  },
  {
    change_type: "threshold_tune",
    decision: "insufficient information",
    rationale: "Description under 20 characters or no expected metric deltas supplied.",
    confidence_band: "LOW",
  },
];
