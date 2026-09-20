// Hand-written mirror of schemas/models.py — only the fields the UI uses.
export type Band = "HIGH" | "AMBIGUOUS" | "LOW";
export type Decision = "pre-authorized" | "requires new submission" | "insufficient information";

export type Verdict = "stable" | "drifted";

export interface MetricDrift { metric: string; delta: number; verdict: Verdict; confidence: number; band: Band }
export interface DriftReport { overall_band: Band; requires_human_review: boolean; metrics: MetricDrift[] }
export interface SubgroupFinding { subgroup: string; metric: string; delta: number; verdict: Verdict; flagged: boolean; band: Band }
export interface FairnessReport { any_flagged: boolean; findings: SubgroupFinding[] }
export interface DriftEntry { snapshot_timestamp: string; drift: DriftReport; fairness: FairnessReport }
export interface PccpDecision { change_type: string; decision: Decision; rationale: string; confidence_band: Band }
export interface Baseline { model_id: string; version: string; risk_classification: string }
