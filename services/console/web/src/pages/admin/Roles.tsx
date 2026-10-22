import { useState } from "react";

import { api, type PermissionGroup, type Role } from "../../api";
import { Badge, Card, Dialog, ErrorAlert, Loading, PageHeader } from "../../components/ui";
import { useAction, useApi } from "../../hooks";

function RoleEditor({ role, groups, onClose, onSaved }: { role: Role | null; groups: PermissionGroup[]; onClose: () => void; onSaved: () => void }) {
  const readOnly = Boolean(role?.builtin);
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [patterns, setPatterns] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const all = patterns.has("*");
  const covered = (key: string, module: string) => all || patterns.has(`${module}.*`) || patterns.has(key);

  const toggle = (pattern: string) =>
    setPatterns((current) => {
      const next = new Set(current);
      if (next.has(pattern)) next.delete(pattern);
      else next.add(pattern);
      return next;
    });
  const toggleModule = (module: string, keys: string[]) =>
    setPatterns((current) => {
      const next = new Set(current);
      if (next.has(`${module}.*`)) next.delete(`${module}.*`);
      else {
        keys.forEach((k) => next.delete(k));
        next.add(`${module}.*`);
      }
      return next;
    });

  const save = useAction(async () => {
    const body = { name, description, permissions: [...patterns] };
    if (role) await api(`/api/admin/roles/${role.id}`, { method: "PUT", body });
    else await api("/api/admin/roles", { method: "POST", body });
    onSaved();
    onClose();
  });

  return (
    <Dialog
      open wide onClose={onClose}
      title={readOnly ? `Built-in role · ${role!.name}` : role ? `Edit role · ${role.name}` : "New role"}
      footer={readOnly ? <button onClick={onClose}>Close</button> : (
        <><button onClick={onClose}>Cancel</button><button className="primary" disabled={!name || patterns.size === 0 || save.pending} onClick={() => void save.run()}>{role ? "Save changes" : "Create role"}</button></>
      )}
    >
      {readOnly && <div className="alert info">Built-in roles can't be changed. Create a custom role to adjust permissions.</div>}
      <div className="grid grid-2">
        <label>Name <span className="hint">lowercase, digits, dashes</span><input value={name} disabled={readOnly} onChange={(e) => setName(e.target.value)} placeholder="feature-reviewer" /></label>
        <label>Description<input value={description} disabled={readOnly} onChange={(e) => setDescription(e.target.value)} placeholder="What is this role for?" /></label>
      </div>
      <label className="check"><input type="checkbox" checked={all} disabled={readOnly} onChange={() => toggle("*")} /><span><b>Everything</b> (<code>*</code>), including permissions added in future versions</span></label>
      {groups.map((group) => {
        const keys = group.permissions.map((p) => p.key);
        const wildcard = patterns.has(`${group.module}.*`);
        return (
          <div key={group.module} className="perm-group">
            <div className="perm-group-header">
              <b>{group.title}</b>
              <label className="check small"><input type="checkbox" checked={all || wildcard} disabled={readOnly || all} onChange={() => toggleModule(group.module, keys)} /><span>All, incl. future (<code>{group.module}.*</code>)</span></label>
            </div>
            <div className="perm-list">
              {group.permissions.map((p) => (
                <label key={p.key} className="check">
                  <input type="checkbox" checked={covered(p.key, group.module)} disabled={readOnly || all || wildcard} onChange={() => toggle(p.key)} />
                  <span><code>{p.key}</code>{p.global_only && <> <Badge plain>global only</Badge></>}<br /><span className="small muted">{p.description}</span></span>
                </label>
              ))}
            </div>
          </div>
        );
      })}
      <ErrorAlert error={save.error} />
    </Dialog>
  );
}

export function Roles() {
  const roles = useApi<Role[]>("/api/admin/roles");
  const groups = useApi<PermissionGroup[]>("/api/admin/permissions");
  const [editing, setEditing] = useState<Role | null | "new">(null);
  const remove = useAction(async (role: Role) => {
    if (!window.confirm(`Delete role ${role.name}?`)) return;
    await api(`/api/admin/roles/${role.id}`, { method: "DELETE" });
    roles.reload();
  });
  if ((roles.loading && !roles.data) || !groups.data) return <Loading />;
  return (
    <>
      <PageHeader title="Roles" subtitle="Roles bundle permissions. Grant them to users or SSO groups on the Access page." actions={<button className="primary" onClick={() => setEditing("new")}>New role</button>} />
      <ErrorAlert error={roles.error ?? remove.error} />
      <Card padded={false}>
        <table>
          <thead><tr><th>Role</th><th>Permissions</th><th>Granted</th><th /></tr></thead>
          <tbody>
            {(roles.data ?? []).map((r) => (
              <tr key={r.id}>
                <td><b>{r.name}</b> {r.builtin && <Badge plain>built-in</Badge>}<div className="small muted">{r.description}</div></td>
                <td>{r.permissions.map((p) => <span key={p} className="chip mono" style={{ margin: "0 4px 4px 0" }}>{p}</span>)}</td>
                <td className="small nowrap">{r.bindings} binding{r.bindings === 1 ? "" : "s"}</td>
                <td>
                  <div className="actions" style={{ justifyContent: "flex-end" }}>
                    <button className="small" onClick={() => setEditing(r)}>{r.builtin ? "View" : "Edit"}</button>
                    {!r.builtin && <button className="small danger" disabled={r.bindings > 0} title={r.bindings ? "Revoke its bindings first" : ""} onClick={() => void remove.run(r)}>Delete</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {editing && <RoleEditor role={editing === "new" ? null : editing} groups={groups.data} onClose={() => setEditing(null)} onSaved={roles.reload} />}
    </>
  );
}
