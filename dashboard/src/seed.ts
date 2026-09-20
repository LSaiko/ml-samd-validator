// Synthetic seed shown when VITE_API_BASE is unset (GitHub Pages). Shapes match the API responses.
import type { Band, Baseline, DriftEntry, PccpDecision } from "./types";

export const seedBaseline: Baseline = { model_id: "cxr-pneumothorax", version: "1.0.0", risk_classification: "II" };

const bandFor = (c: number): Band => (c >= 0.8 ? "HIGH" : c >= 0.55 ? "AMBIGUOUS" : "LOW");
const worst = (bands: Band[]): Band =>
  bands.includes("LOW") ? "LOW" : bands.includes("AMBIGUOUS") ? "AMBIGUOUS" : "HIGH";

// [timestamp, sensitivity delta, specificity delta, auc delta, confidence x3]
const rows: [string, number, number, number, number, number, number][] = [
  ["2026-03-01T00:00:00Z", -0.004, 0.002, -0.003, 0.24, 0.12, 0.31],
  ["2026-04-01T00:00:00Z", -0.012, -0.006, -0.008, 0.61, 0.38, 0.66],
  ["2026-05-01T00:00:00Z", -0.031, -0.014, -0.019, 0.97, 0.72, 0.93],
  ["2026-06-01T00:00:00Z", -0.052, -0.024, -0.033, 0.999, 0.91, 0.995],
];

export const seedDrift: DriftEntry[] = rows.map(([ts, ds, dp, da, cs, cp, ca]) => {
  const metrics = [
    { metric: "sensitivity", delta: ds, confidence: cs, band: bandFor(cs) },
    { metric: "specificity", delta: dp, confidence: cp, band: bandFor(cp) },
    { metric: "auc", delta: da, confidence: ca, band: bandFor(ca) },
  ];
  const overall = worst(metrics.map((m) => m.band));
  const sub = (subgroup: string, k: number) =>
    metrics.map((m) => {
      const delta = +(m.delta * k).toFixed(4);
      const conf = Math.min(0.999, m.confidence * (k > 1 ? 1.05 : 0.8));
      return { subgroup, metric: m.metric, delta, flagged: Math.abs(delta) > 0.05, band: bandFor(conf) };
    });
  const findings = [...sub("female", 1.6), ...sub("male", 0.7), ...sub("age>=65", 1.3)];
  return {
    snapshot_timestamp: ts,
    drift: { overall_band: overall, requires_human_review: overall !== "HIGH", metrics },
    fairness: { any_flagged: findings.some((f) => f.flagged), findings },
  };
});

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
