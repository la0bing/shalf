import { useState } from "react";

import { api, projectPath, type FeatureService, type Table } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, DataTable, ErrorAlert, Loading, PageHeader, RolloutBadge } from "../components/ui";
import { useAction, useApi } from "../hooks";

interface ServingStatus {
  health: { status: string; detail?: string; online_store?: string };
  backend: string;
  views: { view: string; active_version: string | null; status: string }[];
}

function parseJson(text: string, label: string): Record<string, unknown[]> | null {
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${label} is not valid JSON`);
  }
}

export function Serving() {
  const { project, can } = useAuth();
  const status = useApi<ServingStatus>(projectPath(project!, "/serving/status"));
  const services = useApi<FeatureService[]>(can("features.read") ? projectPath(project!, "/features/services") : null);
  const [entities, setEntities] = useState('{"customer_id": [1, 2]}');
  const [service, setService] = useState("");
  const [features, setFeatures] = useState("");
  const [requestData, setRequestData] = useState("");
  const [result, setResult] = useState<Table | null>(null);
  const lookup = useAction(async () => {
    const body = {
      entities: parseJson(entities, "Entities"),
      feature_service: service || null,
      features: service ? null : features.split(/[\s,]+/).filter(Boolean),
      request_data: parseJson(requestData, "Request data"),
    };
    const response = await api<{ results: Record<string, unknown[]> }>(projectPath(project!, "/serving/online"), { method: "POST", body });
    const columns = Object.keys(response.results);
    const n = columns.length ? response.results[columns[0]!]!.length : 0;
    setResult({ columns, rows: Array.from({ length: n }, (_, i) => columns.map((c) => response.results[c]![i])) });
  });

  if (status.loading && !status.data) return <Loading />;
  const s = status.data;
  return (
    <>
      <PageHeader title="Serving" subtitle="Online feature serving for models in production." />
      <ErrorAlert error={status.error} />
      {s && (
        <div className="grid grid-3">
          <Card title="Health">
            <div className="row">
              <Badge tone={s.health.status === "ok" ? "ok" : "danger"}>{s.health.status === "ok" ? "Healthy" : "Unreachable"}</Badge>
              <span className="small muted">{s.health.online_store ?? s.health.detail ?? s.backend}</span>
            </div>
          </Card>
          <Card title="Served views"><div className="stat">{s.views.filter((v) => v.active_version).length}</div><p className="small muted">with an active version</p></Card>
          <Card title="Pending rollouts"><div className="stat">{s.views.filter((v) => v.status === "changed").length}</div><p className="small muted">logic changed, not promoted</p></Card>
        </div>
      )}
      {can("serving.query") && (
        <Card title="Online lookup">
          <div className="grid grid-2">
            <div className="stack">
              <label>Entities <span className="hint">JSON: join key → values</span><textarea value={entities} onChange={(e) => setEntities(e.target.value)} /></label>
              <label>Request data <span className="hint">optional, for on-demand features</span><textarea value={requestData} placeholder='{"amount": [120.0, 15.5]}' onChange={(e) => setRequestData(e.target.value)} /></label>
            </div>
            <div className="stack">
              <label>Feature service
                <select value={service} onChange={(e) => setService(e.target.value)}>
                  <option value="">— pick features instead —</option>
                  {(services.data ?? []).map((fs) => <option key={fs.name} value={fs.name}>{fs.name}</option>)}
                </select>
              </label>
              {!service && <label>Features <span className="hint">view:feature, separated by spaces</span><input value={features} placeholder="customer_txn_stats:txn_count_7d" onChange={(e) => setFeatures(e.target.value)} /></label>}
              <div><button className="primary" onClick={() => void lookup.run()} disabled={lookup.pending}>Look up</button></div>
              <ErrorAlert error={lookup.error} />
            </div>
          </div>
          {result && <div style={{ marginTop: 16 }}><DataTable table={result} /></div>}
        </Card>
      )}
      {s && (
        <Card title="Active versions" padded={false}>
          <table>
            <thead><tr><th>View</th><th>Serving version</th><th>Status</th></tr></thead>
            <tbody>
              {s.views.map((v) => (
                <tr key={v.view}><td>{v.view}</td><td className="mono small">{v.active_version ?? "—"}</td><td><RolloutBadge status={v.status} /></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
