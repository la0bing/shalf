import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth";
import { Empty, Loading, PageHeader } from "./ui";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!me) {
    const returnTo = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?return_to=${returnTo}`} replace />;
  }
  return <>{children}</>;
}

/** Pages scoped to the selected project: explain when there is none. */
export function RequireProject({ permission, children }: { permission: string; children: ReactNode }) {
  const { project, can } = useAuth();
  if (!project) {
    return (
      <>
        <PageHeader title="No project" />
        <Empty>You don't have access to any project yet. Ask an administrator to grant you a role.</Empty>
      </>
    );
  }
  if (!can(permission)) return <Forbidden permission={permission} scope={project} />;
  return <>{children}</>;
}

export function Forbidden({ permission, scope }: { permission: string; scope?: string }) {
  return (
    <>
      <PageHeader title="Access denied" />
      <div className="card card-body stack">
        <p>
          This page needs the <code>{permission}</code> permission{scope && scope !== "*" ? <> in project <b>{scope}</b></> : null}.
        </p>
        <p className="muted">Ask an administrator to grant you a role that includes it.</p>
      </div>
    </>
  );
}
