import { useState } from "react";

import type { AuditEvent } from "../../api";
import { Card, Empty, ErrorAlert, Loading, PageHeader, formatTime } from "../../components/ui";
import { useApi } from "../../hooks";

export function Audit() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const params = new URLSearchParams({ limit: "200" });
  if (action) params.set("action", action);
  if (actor) params.set("actor", actor);
  const events = useApi<AuditEvent[]>(`/api/admin/audit?${params}`);
  return (
    <>
      <PageHeader
        title="Audit log"
        subtitle="Sign-ins, access changes, rollouts and pipeline runs."
        actions={
          <>
            <select aria-label="Action" value={action} onChange={(e) => setAction(e.target.value)} style={{ width: "auto" }}>
              <option value="">All actions</option>
              <option value="auth.">Sign-ins</option>
              <option value="role.">Roles</option>
              <option value="binding.">Access</option>
              <option value="user.">Users</option>
              <option value="features.">Feature rollouts</option>
              <option value="pipelines.">Pipeline runs</option>
              <option value="models.">Models</option>
            </select>
            <input className="search" placeholder="Actor email" value={actor} onChange={(e) => setActor(e.target.value)} aria-label="Actor" />
          </>
        }
      />
      <ErrorAlert error={events.error} />
      <Card padded={false}>
        {events.loading && !events.data ? <Loading /> : (events.data ?? []).length === 0 ? <Empty>No events.</Empty> : (
          <table>
            <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th><th>Project</th><th>Details</th></tr></thead>
            <tbody>
              {events.data!.map((e) => (
                <tr key={e.id}>
                  <td className="small" style={{ whiteSpace: "nowrap" }}>{formatTime(e.at)}</td>
                  <td className="small">{e.actor}</td>
                  <td><code>{e.action}</code></td>
                  <td className="small">{e.target || "—"}</td>
                  <td className="small">{e.project ?? "—"}</td>
                  <td className="small muted wrap">
                    {Object.entries(e.detail).map(([k, v]) => (
                      <span key={k} className="chip mono" style={{ margin: "0 4px 4px 0" }}>{k}: {typeof v === "string" ? v : JSON.stringify(v)}</span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
