import { seedBaseline, seedDrift, seedLog } from "./seed";
import type { Baseline, DriftEntry, PccpDecision } from "./types";

const BASE = import.meta.env.VITE_API_BASE as string | undefined;
const MODEL = (import.meta.env.VITE_MODEL_ID as string | undefined) ?? seedBaseline.model_id;

export interface Data { baseline: Baseline; drift: DriftEntry[]; log: PccpDecision[]; source: "api" | "seed" }

const get = <T,>(path: string): Promise<T> =>
  fetch(`${BASE}${path}`).then((r) => (r.ok ? r.json() : Promise.reject(`${r.status} ${path}`)));

export async function load(): Promise<Data> {
  if (!BASE) return { baseline: seedBaseline, drift: seedDrift, log: seedLog, source: "seed" };
  const [drift, log, card] = await Promise.all([
    get<DriftEntry[]>(`/drift/${MODEL}`),
    get<PccpDecision[]>(`/pccp/log/${MODEL}`),
    get<{ baseline: Baseline }>(`/model-card/${MODEL}`),
  ]);
  return { baseline: card.baseline, drift, log, source: "api" };
}
