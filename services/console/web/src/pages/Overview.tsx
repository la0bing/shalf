import { Link } from "react-router-dom";

import { projectPath, type FeatureView } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, ModuleStatus, PageHeader, RolloutBadge } from "../components/ui";
import { useApi } from "../hooks";

const ROUTES: Record<string, string> = {
  features: "/features", pipelines: "/pipelines", serving: "/serving", models: "/models",
  training: "/training", monitoring: "/monitoring", admin: "/admin/users",
};

export function Overview() {
  const { me, modules, projects, project, can } = useAuth();
  const views = useApi<FeatureView[]>(project && can("features.read") ? projectPath(project, "/features/views") : null);
  const attention = (views.data ?? []).filter((v) => v.rollout && v.rollout.status !== "unchanged");

  return (
    <>
      <PageHeader title={`Welcome${me?.name ? `, ${me.name.split(" ")[0]}` : ""}`} subtitle="Everything running on the platform, in one place." />

      <div className="grid grid-auto">
        {modules.map((m) => {
          const body = (
            <>
              <div className="title">{m.title} <ModuleStatus status={m.status} /></div>
              <p className="muted small">{m.description}</p>
              {!m.accessible && <span className="small muted">No access · needs <code>{m.read_permission}</code></span>}
            </>
          );
          return m.accessible && m.status !== "planned" ? (
            <Link key={m.key} to={ROUTES[m.key] ?? "/"} className="card module-card">{body}</Link>
          ) : (
            <div key={m.key} className={`card module-card ${m.accessible ? "" : "locked"}`}>
              {m.accessible ? <Link to={ROUTES[m.key] ?? "/"} style={{ color: "inherit" }}>{body}</Link> : body}
            </div>
          );
        })}
      </div>

      <div className="grid grid-2">
        <Card title="Your projects" padded={false}>
          {projects.length === 0 ? (
            <p className="card-body muted">No project access yet. Ask an administrator for a role.</p>
          ) : (
            <table>
              <thead><tr><th>Project</th><th>Runs on</th><th>Your permissions</th></tr></thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.name}>
                    <td><b>{p.name}</b>{p.description && <div className="small muted">{p.description}</div>}</td>
                    <td><Badge plain>{p.backend}</Badge> {p.pipeline_runner && <Badge plain>{p.pipeline_runner} runner</Badge>}</td>
                    <td className="small">{p.permissions.length} permissions</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title={`Needs attention${project ? ` · ${project}` : ""}`} padded={false}>
          {!can("features.read") ? (
            <p className="card-body muted">You can't see feature views in this project.</p>
          ) : attention.length === 0 ? (
            <p className="card-body muted">{views.loading ? "Loading…" : "All feature views are live on their current logic."}</p>
          ) : (
            <table>
              <thead><tr><th>Feature view</th><th>Status</th></tr></thead>
              <tbody>
                {attention.map((v) => (
                  <tr key={v.name}>
                    <td><Link to={`/features/${encodeURIComponent(v.name)}`}>{v.name}</Link></td>
                    <td><RolloutBadge status={v.rollout?.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  );
}
