import { api, type ModelVersion } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader } from "../components/ui";
import { useAction, useApi } from "../hooks";

const STAGE_TONE: Record<string, "ok" | "info" | "neutral"> = { production: "ok", staging: "info", archived: "neutral" };

export function Models() {
  const { can } = useAuth();
  const models = useApi<ModelVersion[]>("/api/models");
  const promote = useAction(async (m: ModelVersion, stage: string) => {
    await api(`/api/models/${encodeURIComponent(m.name)}/versions/${encodeURIComponent(m.version)}/promote`, { method: "POST", body: { stage } });
    models.reload();
  });
  if (models.loading && !models.data) return <Loading />;
  return (
    <>
      <PageHeader title={<span className="row">Models <Badge tone="info" plain>Preview</Badge></span>} subtitle="Registered model versions and the feature services they were trained on." />
      <ErrorAlert error={models.error ?? promote.error} />
      <Card padded={false}>
        {(models.data ?? []).length === 0 ? <Empty>No models registered yet. Training jobs register versions through shalf-models.</Empty> : (
          <table>
            <thead><tr><th>Model</th><th>Version</th><th>Stage</th><th>Feature service</th><th>Metrics</th><th>Framework</th><th /></tr></thead>
            <tbody>
              {models.data!.map((m) => (
                <tr key={`${m.name}@${m.version}`}>
                  <td><b>{m.name}</b><div className="small muted mono">{m.uri}</div></td>
                  <td className="mono">{m.version}</td>
                  <td><Badge tone={STAGE_TONE[m.stage] ?? "neutral"}>{m.stage}</Badge></td>
                  <td className="mono small">{m.feature_service}</td>
                  <td className="small">{Object.entries(m.metrics).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}</td>
                  <td className="small">{m.framework}</td>
                  <td>
                    {can("models.promote", "*") && (
                      <select aria-label={`Stage of ${m.name} ${m.version}`} value={m.stage} disabled={promote.pending} onChange={(e) => void promote.run(m, e.target.value)} style={{ width: "auto" }}>
                        <option value="staging">staging</option>
                        <option value="production">production</option>
                        <option value="archived">archived</option>
                      </select>
                    )}
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
