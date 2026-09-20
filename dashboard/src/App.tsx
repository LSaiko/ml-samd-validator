import { useEffect, useState } from "react";
import { load, type Data } from "./api";
import { DecisionLog, DriftChart, FairnessTable } from "./components";
import "./app.css";

export default function App() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    load().then(setData, (e) => setError(String(e)));
  }, []);
  if (error) return <main><p className="review">Failed to load: {error}</p></main>;
  if (!data) return <main><p className="muted">Loading...</p></main>;
  const latest = data.drift[data.drift.length - 1];
  return (
    <main>
      <header>
        <div>
          <h1>ml-samd-validator</h1>
          <p className="muted">
            The Inspector: evaluates a model against a locked baseline and PCCP under FDA GMLP and flags deviations by three-band confidence.
          </p>
          <p className="muted">
            model <code>{data.baseline.model_id}</code> v{data.baseline.version} · FDA SaMD class {data.baseline.risk_classification} · source: {data.source}
          </p>
        </div>
        <span className="badge">evidence only · human review required</span>
      </header>

      <section>
        <h2>Drift over time</h2>
        <p className="muted">Point colour = confidence that the metric moved (HIGH cyan, AMBIGUOUS orange, LOW slate). Overall band per snapshot below.</p>
        <DriftChart entries={data.drift} />
      </section>

      <section>
        <h2>PCCP decision log</h2>
        <DecisionLog log={data.log} />
      </section>

      <section>
        <h2>Subgroup fairness · {latest?.snapshot_timestamp.slice(0, 10)}</h2>
        <p className="muted">Delta vs locked baseline per subgroup; |delta| &gt; 0.05 is flagged. Aggregate pass does not establish subgroup equity.</p>
        {latest && <FairnessTable entry={latest} />}
      </section>
    </main>
  );
}
