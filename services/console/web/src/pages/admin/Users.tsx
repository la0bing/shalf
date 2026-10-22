import { useMemo, useState } from "react";

import { api, type Binding, type User } from "../../api";
import { useAuth } from "../../auth";
import { Badge, Card, Dialog, ErrorAlert, Loading, PageHeader, relativeTime } from "../../components/ui";
import { useAction, useApi } from "../../hooks";

function NewUserDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const create = useAction(async () => {
    await api("/api/admin/users", { method: "POST", body: { email, name, password: password || null } });
    onCreated();
    onClose();
  });
  return (
    <Dialog open onClose={onClose} title="Add user" footer={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!email || create.pending} onClick={() => void create.run()}>Add user</button></>}>
      <p className="small muted">SSO users are created automatically on first sign-in; add users here to pre-assign access or to give them a local password.</p>
      <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label>Local password <span className="hint">optional, at least 12 characters; leave empty for SSO-only</span><input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <ErrorAlert error={create.error} />
    </Dialog>
  );
}

export function Users() {
  const { me, can } = useAuth();
  const users = useApi<User[]>("/api/admin/users");
  const bindings = useApi<Binding[]>("/api/admin/bindings");
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const toggle = useAction(async (user: User) => {
    await api(`/api/admin/users/${user.id}`, { method: "PATCH", body: { disabled: !user.disabled } });
    users.reload();
  });
  const rolesOf = useMemo(() => {
    const map = new Map<string, Binding[]>();
    for (const b of bindings.data ?? []) if (b.subject_type === "user") map.set(b.subject, [...(map.get(b.subject) ?? []), b]);
    return map;
  }, [bindings.data]);
  const manage = can("admin.users.manage", "*");

  if (users.loading && !users.data) return <Loading />;
  const shown = (users.data ?? []).filter((u) => !query || u.email.includes(query.toLowerCase()) || u.name.toLowerCase().includes(query.toLowerCase()));
  return (
    <>
      <PageHeader
        title="Users"
        subtitle="Everyone who has signed in or was added by an admin. Access comes from role bindings on the user or their SSO groups."
        actions={<><input className="search" placeholder="Search users…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search users" />{manage && <button className="primary" onClick={() => setAdding(true)}>Add user</button>}</>}
      />
      <ErrorAlert error={users.error ?? toggle.error} />
      <Card padded={false}>
        <table>
          <thead><tr><th>User</th><th>Sign-in</th><th>Direct roles</th><th>Last sign-in</th><th>Status</th><th /></tr></thead>
          <tbody>
            {shown.map((u) => (
              <tr key={u.id}>
                <td><b>{u.name || u.email}</b><div className="small muted">{u.email}</div></td>
                <td className="small">{u.source === "local" ? (u.has_password ? "Local password" : "SSO only") : `SSO · ${u.source}`}</td>
                <td>{(rolesOf.get(u.email) ?? []).map((b) => <span key={b.id} className="chip" style={{ margin: "0 4px 4px 0" }}>{b.role}{b.scope !== "*" ? ` · ${b.scope.replace("project:", "")}` : ""}</span>)}{!rolesOf.get(u.email) && <span className="small muted">via groups only</span>}</td>
                <td className="small">{relativeTime(u.last_login_at)}</td>
                <td>{u.disabled ? <Badge tone="danger">Disabled</Badge> : <Badge tone="ok">Active</Badge>}</td>
                <td>{manage && u.email !== me?.email && <button className="small" onClick={() => void toggle.run(u)}>{u.disabled ? "Enable" : "Disable"}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {adding && <NewUserDialog onClose={() => setAdding(false)} onCreated={users.reload} />}
    </>
  );
}
