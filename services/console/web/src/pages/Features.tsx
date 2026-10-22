import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, projectPath, type FeatureService, type FeatureView } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, RolloutBadge } from "../components/ui";
import { useAction, useApi } from "../hooks";

const KIND: Record<string, string> = {
  batch: "Source", derived: "Derived", aggregation: "Aggregation", on_demand: "On-demand",
};

export function Features() {
  const { project, can } = useAuth();
  const navigate = useNavigate();
  const views = useApi<FeatureView[]>(projectPath(project!, "/features/views"));
  const services = useApi<FeatureService[]>(projectPath(project!, "/features/services"));
  const [query, setQuery] = useState("");
  const changed = (views.data ?? []).filter((v) => v.rollout?.status === "changed");
  const promote = useAction(async () => {
    await api(projectPath(project!, "/features/promote"), { method: "POST", body: { views: null } });
    views.reload();
  });

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return (views.data ?? []).filter(
      (v) => !q || v.name.includes(q) || v.features.some((f) => f.name.includes(q)) || v.owner.includes(q),
    );
  }, [views.data, query]);

  if (views.loading && !views.data) return <Loading />;
  return (
    <>
      <PageHeader
        title="Features"
        subtitle={`Feature views in ${project}, in dependency order.`}
        actions={
          <>
            <input className="search" placeholder="Filter views or features…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter" />
            {can("features.promote") && changed.length > 0 && (
              <button className="primary" disabled={promote.pending} onClick={() => void promote.run()}>
                Promote {changed.length} changed view{changed.length > 1 ? "s" : ""}
              </button>
            )}
          </>
        }
      />
      <ErrorAlert error={views.error ?? promote.error} />
      <Card padded={false}>
        {filtered.length === 0 ? (
          <Empty>No feature views match.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>View</th><th>Kind</th><th>Entities</th><th>Features</th><th>Version</th><th>Status</th><th>Owner</th></tr>
              </thead>
              <tbody>
                {filtered.map((v) => (
                  <tr key={v.name} className="clickable" onClick={() => navigate(`/features/${encodeURIComponent(v.name)}`)}>
                    <td><b>{v.name}</b>{v.description && <div className="small muted">{v.description}</div>}</td>
                    <td><Badge plain>{KIND[v.kind] ?? v.kind}</Badge>{!v.online && v.kind !== "on_demand" && <> <Badge plain>offline</Badge></>}</td>
                    <td className="small">{v.join_keys.join(", ") || "—"}</td>
                    <td className="small">{v.features.length}</td>
                    <td className="mono small">{v.version}</td>
                    <td><RolloutBadge status={v.rollout?.status} /></td>
                    <td className="small">{v.owner || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Feature services" padded={false}>
        {(services.data ?? []).length === 0 ? (
          <Empty>No feature services defined.</Empty>
        ) : (
          <table>
            <thead><tr><th>Service</th><th>Features</th><th>Owner</th></tr></thead>
            <tbody>
              {services.data!.map((s) => (
                <tr key={s.name}>
                  <td><b>{s.name}</b>{s.description && <div className="small muted">{s.description}</div>}</td>
                  <td>{s.features.map((f) => <span key={f} className="chip mono" style={{ margin: "0 4px 4px 0" }}>{f}</span>)}</td>
                  <td className="small">{s.owner || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
