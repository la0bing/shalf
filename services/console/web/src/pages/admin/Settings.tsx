import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader } from "../../components/ui";
import { useApi } from "../../hooks";

interface SettingsData {
  local_login: boolean;
  session_ttl_hours: number;
  bootstrap_admins: string[];
  oidc: { id: string; name: string; issuer: string; client_id: string; scopes: string[]; groups_claim: string; allowed_domains: string[] }[];
  projects: { name: string; backend: string; pipeline_runner: string | null }[];
  model_registry: string;
}

export function Settings() {
  const settings = useApi<SettingsData>("/api/admin/settings");
  if (settings.loading && !settings.data) return <Loading />;
  const s = settings.data;
  return (
    <>
      <PageHeader title="SSO & settings" subtitle="Read-only: configured in the console's config file (console.yaml) and environment." />
      <ErrorAlert error={settings.error} />
      {s && (
        <>
          <Card title="Single sign-on (OpenID Connect)" padded={false}>
            {s.oidc.length === 0 ? <Empty>No identity provider configured.</Empty> : (
              <table>
                <thead><tr><th>Provider</th><th>Issuer</th><th>Client ID</th><th>Scopes</th><th>Groups claim</th><th>Allowed domains</th></tr></thead>
                <tbody>
                  {s.oidc.map((p) => (
                    <tr key={p.id}>
                      <td><b>{p.name}</b><div className="small muted mono">/auth/oidc/{p.id}/callback</div></td>
                      <td className="mono small">{p.issuer}</td>
                      <td className="mono small">{p.client_id}</td>
                      <td className="small">{p.scopes.join(" ")}</td>
                      <td className="mono small">{p.groups_claim}</td>
                      <td className="small">{p.allowed_domains.join(", ") || "any"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          <div className="grid grid-2">
            <Card title="Sign-in">
              <dl className="kv small">
                <dt>Local accounts</dt><dd>{s.local_login ? <Badge tone="warn">Enabled</Badge> : <Badge tone="ok">Disabled (SSO only)</Badge>}</dd>
                <dt>Session lifetime</dt><dd>{s.session_ttl_hours} h</dd>
                <dt>Break-glass admins</dt><dd>{s.bootstrap_admins.join(", ") || "—"}</dd>
              </dl>
            </Card>
            <Card title="Projects" padded={false}>
              <table>
                <thead><tr><th>Project</th><th>Backend</th><th>Pipeline runner</th></tr></thead>
                <tbody>{s.projects.map((p) => <tr key={p.name}><td>{p.name}</td><td>{p.backend}</td><td>{p.pipeline_runner ?? "—"}</td></tr>)}</tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
