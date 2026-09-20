import { CategoryScale, Chart, Legend, LinearScale, LineElement, PointElement, Tooltip } from "chart.js";
import { Line } from "react-chartjs-2";
import type { Band, Decision, DriftEntry, PccpDecision } from "./types";

Chart.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

export const BAND_COLOR: Record<Band, string> = { HIGH: "#22d3ee", AMBIGUOUS: "#f97316", LOW: "#94a3b8" };
const DECISION_BAND: Record<Decision, Band> = {
  "pre-authorized": "HIGH",
  "requires new submission": "AMBIGUOUS",
  "insufficient information": "LOW",
};
const DASHES = [[], [8, 4], [2, 4]];
const day = (ts: string) => ts.slice(0, 10);
const signed = (n: number) => (n >= 0 ? "+" : "") + n.toFixed(4);

export const Chip = ({ band, label }: { band: Band; label?: string }) => (
  <span className="chip" style={{ background: BAND_COLOR[band] }}>{label ?? band}</span>
);

const zeroLine = {
  id: "zeroLine",
  afterDraw(chart: Chart) {
    const { ctx, chartArea, scales } = chart;
    const y = scales.y.getPixelForValue(0);
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "rgba(148,163,184,0.45)";
    ctx.beginPath();
    ctx.moveTo(chartArea.left, y);
    ctx.lineTo(chartArea.right, y);
    ctx.stroke();
    ctx.restore();
  },
};

const axis = { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.12)" } };

export function DriftChart({ entries }: { entries: DriftEntry[] }) {
  const metrics = [...new Set(entries.flatMap((e) => e.drift.metrics.map((m) => m.metric)))];
  const data = {
    labels: entries.map((e) => day(e.snapshot_timestamp)),
    datasets: metrics.map((metric, i) => {
      const pts = entries.map((e) => e.drift.metrics.find((m) => m.metric === metric));
      return {
        label: metric,
        data: pts.map((p) => p?.delta ?? null),
        borderColor: "#cbd5e1",
        borderDash: DASHES[i % DASHES.length],
        borderWidth: 1.5,
        pointRadius: 6,
        pointBackgroundColor: pts.map((p) => (p ? BAND_COLOR[p.band] : "transparent")),
        pointBorderColor: "#0f172a",
        tension: 0.2,
      };
    }),
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: axis,
      y: { ...axis, title: { display: true, text: "delta vs locked baseline", color: "#94a3b8" } },
    },
    plugins: { legend: { labels: { color: "#e2e8f0" } } },
  };
  return (
    <>
      <div className="chart"><Line data={data} options={options} plugins={[zeroLine]} /></div>
      <div className="chips">
        {entries.map((e) => (
          <span key={e.snapshot_timestamp} className="snap">
            <small className="muted">{day(e.snapshot_timestamp)}</small>
            <Chip
              band={e.drift.overall_band}
              label={`${e.drift.overall_band} · ${e.drift.metrics.some((m) => m.verdict === "drifted") ? "drifted" : "stable"}`}
            />
            {e.drift.requires_human_review && <small className="review">review</small>}
          </span>
        ))}
      </div>
    </>
  );
}

export const DecisionLog = ({ log }: { log: PccpDecision[] }) => (
  <table>
    <thead><tr><th>#</th><th>Change type</th><th>Decision</th><th>Rationale</th><th>Confidence</th></tr></thead>
    <tbody>
      {log.map((d, i) => (
        <tr key={i}>
          <td>{i + 1}</td>
          <td>{d.change_type}</td>
          <td><Chip band={DECISION_BAND[d.decision]} label={d.decision} /></td>
          <td className="muted">{d.rationale}</td>
          <td><Chip band={d.confidence_band} /></td>
        </tr>
      ))}
    </tbody>
  </table>
);

export function FairnessTable({ entry }: { entry: DriftEntry }) {
  const { findings } = entry.fairness;
  const metrics = [...new Set(findings.map((f) => f.metric))];
  const groups = [...new Set(findings.map((f) => f.subgroup))];
  const cell = (g: string, m: string) => findings.find((f) => f.subgroup === g && f.metric === m);
  return (
    <table>
      <thead><tr><th>Subgroup</th>{metrics.map((m) => <th key={m}>{m}</th>)}</tr></thead>
      <tbody>
        {groups.map((g) => {
          const flagged = metrics.some((m) => cell(g, m)?.flagged);
          return (
            <tr key={g} className={flagged ? "flagged" : ""}>
              <td>{g}{flagged && <small className="review">flagged</small>}</td>
              {metrics.map((m) => {
                const f = cell(g, m);
                return <td key={m}>{f ? <>{signed(f.delta)} <Chip band={f.band} label={`${f.band} · ${f.verdict}`} /></> : "-"}</td>;
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
