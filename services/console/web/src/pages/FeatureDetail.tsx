import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, projectPath, type FeatureView, type Table } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, DataTable, ErrorAlert, Loading, PageHeader, RolloutBadge, formatTime } from "../components/ui";
import { useAction, useApi } from "../hooks";

export function FeatureDetail() {
  const { view = "" } = useParams();
  const { project, can } = useAuth();
  const detail = useApi<FeatureView>(projectPath(project!, `/features/views/${encodeURIComponent(view)}`));
  const [tab, setTab] = useState<"schema" | "preview" | "definition">("schema");
  const preview = useApi<Table>(
    tab === "preview" && can("features.preview") ? projectPath(project!, `/features/views/${encodeURIComponent(view)}/preview?limit=50`) : null,
  );
  const promote = useAction(async () => {
    await api(projectPath(project!, "/features/promote"), { method: "POST", body: { views: [view] } });
    detail.reload();
  });

  if (detail.loading && !detail.data) return <Loading />;
  if (detail.error) return <ErrorAlert error={detail.error} />;
  const v = detail.data!;
  const rollout = v.rollout;

  return (
    <>
      <PageHeader
        title={<span className="row">{v.name} <RolloutBadge status={rollout?.status} /></span>}
        subtitle={v.description || `${v.kind} feature view`}
        actions={
          <>
            <Link to="/features" className="button">All views</Link>
            {rollout?.status === "changed" && can("features.promote") && (
              <button className="primary" onClick={() => void promote.run()} disabled={promote.pending}>Promote to {rollout.code_version}</button>
            )}
          </>
        }
      />
      <ErrorAlert error={promote.error} />
      <div className="grid grid-3">
        <Card title="Lineage">
          <div className="lineage">
            {v.upstream.length ? v.upstream.map((u) => <Link key={u} className="chip" to={`/features/${encodeURIComponent(u)}`}>{u}</Link>) : <span className="muted small">source</span>}
            <span className="arrow">→</span>
            <span className="chip" style={{ borderColor: "var(--accent)" }}><b>{v.name}</b></span>
            <span className="arrow">→</span>
            {v.downstream.length ? v.downstream.map((d) => <Link key={d} className="chip" to={`/features/${encodeURIComponent(d)}`}>{d}</Link>) : <span className="muted small">none</span>}
          </div>
        </Card>
        <Card title="Rollout">
          <dl className="kv small">
            <dt>Code version</dt><dd className="mono">{rollout?.code_version ?? v.version}</dd>
            <dt>Serving version</dt><dd className="mono">{rollout ? rollout.active_version ?? "—" : "computed on request"}</dd>
            <dt>Materialised until</dt><dd>{formatTime(rollout?.code_version_materialized_until)}</dd>
            <dt>Used by</dt><dd>{rollout?.feature_services.length ? rollout.feature_services.join(", ") : "—"}</dd>
          </dl>
        </Card>
        <Card title="Properties">
          <dl className="kv small">
            <dt>Entities</dt><dd>{v.entities.join(", ") || "—"} <span className="muted">({v.join_keys.join(", ")})</span></dd>
            <dt>TTL</dt><dd>{v.ttl_seconds ? `${Math.round(v.ttl_seconds / 3600)} h` : "none"}</dd>
            <dt>Online</dt><dd>{v.online ? "yes" : "no"}</dd>
            <dt>Owner</dt><dd>{v.owner || "—"}</dd>
          </dl>
        </Card>
      </div>

      <Card padded={false}>
        <div className="tabs" role="tablist">
          <button className={tab === "schema" ? "active" : ""} onClick={() => setTab("schema")}>Features ({v.features.length})</button>
          {can("features.preview") && <button className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}>Preview rows</button>}
          <button className={tab === "definition" ? "active" : ""} onClick={() => setTab("definition")}>Definition</button>
        </div>
        {tab === "schema" && (
          <table>
            <thead><tr><th>Feature</th><th>Type</th><th>Reference</th><th>Description</th></tr></thead>
            <tbody>
              {v.features.map((f) => (
                <tr key={f.name}>
                  <td><b>{f.name}</b></td>
                  <td><Badge plain>{f.dtype}</Badge></td>
                  <td className="mono small">{v.name}:{f.name}</td>
                  <td className="small muted">{f.description || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "preview" && (
          <div className="card-body">
            {preview.loading ? <Loading /> : preview.error ? <ErrorAlert error={preview.error} /> : preview.data && <DataTable table={preview.data} />}
          </div>
        )}
        {tab === "definition" && (
          <div className="card-body">
            <pre className="log">{JSON.stringify({ source: v.source, transformation: v.transformation, request_schema: v.request_schema, tags: v.tags }, null, 2)}</pre>
          </div>
        )}
      </Card>
    </>
  );
}
