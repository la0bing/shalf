// Typed client for the console API. Cookies carry the session; state-changing
// requests echo the CSRF cookie in a header (double-submit).

export type Status = "ready" | "preview" | "planned";

export interface Me {
  email: string;
  name: string;
  groups: string[];
  auth_source: string;
  permissions: Record<string, string[]>;
}

export interface Module {
  key: string;
  title: string;
  description: string;
  status: Status;
  read_permission: string;
  project_scoped: boolean;
  order: number;
  accessible: boolean;
}

export interface Project {
  name: string;
  description: string;
  backend: string;
  pipeline_runner: string | null;
  permissions: string[];
}

export interface Providers {
  local: boolean;
  oidc: { id: string; name: string; login_url: string }[];
}

export interface Field {
  name: string;
  dtype: string;
  description: string;
}

export interface Rollout {
  view: string;
  code_version: string;
  active_version: string | null;
  status: "new" | "unchanged" | "changed";
  code_version_materialized_until: string | null;
  feature_services: string[];
}

export interface FeatureView {
  name: string;
  kind: string;
  entities: string[];
  join_keys: string[];
  features: Field[];
  ttl_seconds: number | null;
  online: boolean;
  version: string;
  upstream: string[];
  downstream: string[];
  description: string;
  owner: string;
  tags: Record<string, string>;
  rollout: Rollout | null;
  source?: Record<string, unknown>;
  transformation?: Record<string, unknown>;
  request_schema?: Field[];
}

export interface FeatureService {
  name: string;
  features: string[];
  description: string;
  owner: string;
}

export interface Pipeline {
  name: string;
  schedule: string | null;
  dbt_select?: string | null;
  views?: string | string[];
}

export interface PipelineRun {
  id: string;
  pipeline: string;
  status: "running" | "succeeded" | "failed";
  args: { start?: string | null; end?: string | null; promote?: boolean };
  triggered_by: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown>;
  log?: string;
}

export interface Table {
  columns: string[];
  rows: unknown[][];
}

export interface ModelVersion {
  name: string;
  version: string;
  uri: string;
  feature_service: string;
  framework: string;
  stage: string;
  metrics: Record<string, number>;
}

export interface Role {
  id: number;
  name: string;
  description: string;
  builtin: boolean;
  permissions: string[];
  bindings: number;
}

export interface PermissionGroup {
  module: string;
  title: string;
  permissions: { key: string; description: string; global_only: boolean }[];
}

export interface User {
  id: number;
  email: string;
  name: string;
  source: string;
  disabled: boolean;
  has_password: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface Binding {
  id: number;
  subject_type: "user" | "group";
  subject: string;
  role: string;
  scope: string;
  created_at: string | null;
  created_by: string;
}

export interface AuditEvent {
  id: number;
  at: string;
  actor: string;
  action: string;
  target: string;
  project: string | null;
  detail: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function csrfToken(): string {
  const cookie = document.cookie.split("; ").find((c) => c.startsWith("shalf_csrf="));
  return cookie ? decodeURIComponent(cookie.slice("shalf_csrf=".length)) : "";
}

function describe(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
      .join("; ");
  }
  return fallback;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, describe(data?.detail, response.statusText));
  return data as T;
}

export const projectPath = (project: string, path: string) =>
  `/api/projects/${encodeURIComponent(project)}${path}`;
