import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth";
import { ModuleStatus } from "./ui";

const ROUTES: Record<string, string> = {
  features: "/features",
  pipelines: "/pipelines",
  serving: "/serving",
  models: "/models",
  training: "/training",
  monitoring: "/monitoring",
};

const ADMIN_PAGES: [string, string, string][] = [
  ["/admin/users", "Users", "admin.users.read"],
  ["/admin/roles", "Roles", "admin.roles.manage"],
  ["/admin/access", "Access", "admin.bindings.manage"],
  ["/admin/audit", "Audit log", "admin.audit.read"],
  ["/admin/settings", "SSO & settings", "admin.settings.read"],
];

export function Logo() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 16 16"><path d="M3 4.5h10M3 8h7M3 11.5h10" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" /></svg>
    </span>
  );
}

export function Layout() {
  const { me, modules, projects, project, setProject, logout, can } = useAuth();
  const navigate = useNavigate();
  const adminPages = ADMIN_PAGES.filter(([, , perm]) => can(perm, "*"));
  const initials = (me?.name || me?.email || "?").split(/[\s@.]/).filter(Boolean).slice(0, 2).map((s) => s[0]!.toUpperCase()).join("");

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand"><Logo /> shalf</div>
        <NavLink to="/" end className="nav-link">Overview</NavLink>
        <div className="nav-section">Platform</div>
        {modules
          .filter((m) => m.key !== "admin" && ROUTES[m.key])
          .map((m) =>
            m.accessible ? (
              <NavLink key={m.key} to={ROUTES[m.key]!} className="nav-link">
                {m.title} <ModuleStatus status={m.status} />
              </NavLink>
            ) : null,
          )}
        {adminPages.length > 0 && (
          <>
            <div className="nav-section">Administration</div>
            {adminPages.map(([to, label]) => (
              <NavLink key={to} to={to} className="nav-link">{label}</NavLink>
            ))}
          </>
        )}
      </nav>
      <div className="main">
        <header className="topbar">
          <div className="row">
            {projects.length > 0 ? (
              <label className="row" style={{ flexDirection: "row", alignItems: "center", fontWeight: 500 }}>
                <span className="muted small">Project</span>
                <select aria-label="Project" value={project ?? ""} onChange={(e) => setProject(e.target.value)} style={{ width: "auto", minWidth: 160 }}>
                  {projects.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
                </select>
              </label>
            ) : (
              <span className="muted small">No project access yet</span>
            )}
          </div>
          <div className="user-chip">
            <div className="stack" style={{ gap: 0, textAlign: "right" }}>
              <span style={{ color: "var(--text)", fontWeight: 550 }}>{me?.name || me?.email}</span>
              <span className="small muted">{me?.auth_source === "local" ? "Local account" : `SSO · ${me?.auth_source}`}</span>
            </div>
            <span className="avatar" aria-hidden="true">{initials}</span>
            <button className="small" onClick={async () => { await logout(); navigate("/login"); }}>Sign out</button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
