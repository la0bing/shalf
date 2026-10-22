import { useState } from "react";

import { api, type Binding, type Role, type User } from "../../api";
import { useAuth } from "../../auth";
import { Badge, Card, Dialog, Empty, ErrorAlert, Loading, PageHeader, relativeTime } from "../../components/ui";
import { useAction, useApi } from "../../hooks";

function GrantDialog({ roles, users, onClose, onCreated }: { roles: Role[]; users: User[]; onClose: () => void; onCreated: () => void }) {
  const { projects } = useAuth();
  const [subjectType, setSubjectType] = useState<"user" | "group">("group");
  const [subject, setSubject] = useState("");
  const [role, setRole] = useState(roles[0]?.name ?? "");
  const [scope, setScope] = useState("*");
  const grant = useAction(async () => {
    await api("/api/admin/bindings", { method: "POST", body: { subject_type: subjectType, subject, role, scope } });
    onCreated();
    onClose();
  });
  return (
    <Dialog open onClose={onClose} title="Grant access" footer={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!subject || !role || grant.pending} onClick={() => void grant.run()}>Grant</button></>}>
      <div className="grid grid-2">
        <label>Grant to
          <select value={subjectType} onChange={(e) => setSubjectType(e.target.value as "user" | "group")}>
            <option value="group">SSO group</option>
            <option value="user">User</option>
          </select>
        </label>
        <label>{subjectType === "group" ? "Group name" : "User email"}
          <input list="known-users" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={subjectType === "group" ? "ml-team" : "ana@example.com"} />
          {subjectType === "user" && <datalist id="known-users">{users.map((u) => <option key={u.id} value={u.email} />)}</datalist>}
        </label>
        <label>Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((r) => <option key={r.id} value={r.name}>{r.name}{r.builtin ? "" : " (custom)"}</option>)}
          </select>
        </label>
        <label>Scope
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="*">All projects (global)</option>
            {projects.map((p) => <option key={p.name} value={`project:${p.name}`}>Project: {p.name}</option>)}
          </select>
        </label>
      </div>
      <p className="small muted">
        {subjectType === "group" ? "Group names must match the groups claim your identity provider sends. Membership is then managed in the IdP." : "Users don't need to have signed in yet."}
        {scope !== "*" && " Admin permissions only apply in global bindings."}
      </p>
      <ErrorAlert error={grant.error} />
    </Dialog>
  );
}

export function Access() {
  const bindings = useApi<Binding[]>("/api/admin/bindings");
  const roles = useApi<Role[]>("/api/admin/roles");
  const users = useApi<User[]>("/api/admin/users");
  const [granting, setGranting] = useState(false);
  const revoke = useAction(async (b: Binding) => {
    if (!window.confirm(`Revoke ${b.role} from ${b.subject}?`)) return;
    await api(`/api/admin/bindings/${b.id}`, { method: "DELETE" });
    bindings.reload();
  });
  if (bindings.loading && !bindings.data) return <Loading />;
  return (
    <>
      <PageHeader title="Access" subtitle="Who has which role, and where. Bindings on SSO groups follow group membership in your identity provider." actions={<button className="primary" onClick={() => setGranting(true)} disabled={!roles.data}>Grant access</button>} />
      <ErrorAlert error={bindings.error ?? revoke.error} />
      <Card padded={false}>
        {(bindings.data ?? []).length === 0 ? <Empty>No bindings.</Empty> : (
          <table>
            <thead><tr><th>Subject</th><th>Role</th><th>Scope</th><th>Granted by</th><th /></tr></thead>
            <tbody>
              {bindings.data!.map((b) => (
                <tr key={b.id}>
                  <td><Badge plain>{b.subject_type === "group" ? "Group" : "User"}</Badge> <b>{b.subject}</b></td>
                  <td>{b.role}</td>
                  <td>{b.scope === "*" ? <Badge tone="accent" plain>Global</Badge> : <span className="chip">{b.scope.replace("project:", "")}</span>}</td>
                  <td className="small">{b.created_by} <span className="muted">· {relativeTime(b.created_at)}</span></td>
                  <td><button className="small danger" onClick={() => void revoke.run(b)}>Revoke</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {granting && roles.data && <GrantDialog roles={roles.data} users={users.data ?? []} onClose={() => setGranting(false)} onCreated={bindings.reload} />}
    </>
  );
}
