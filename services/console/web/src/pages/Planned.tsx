import { useAuth } from "../auth";
import { Badge, Card, PageHeader } from "../components/ui";

const PLANS: Record<string, string[]> = {
  training: [
    "Experiments and training runs, with parameters, metrics and artefacts",
    "Point-in-time training datasets built from a feature service",
    "One-click registration of a run's model into the model registry",
  ],
  monitoring: [
    "Feature and prediction drift against the training distribution",
    "Freshness SLAs per feature view, from materialisation watermarks",
    "Data-quality results from dbt tests over time",
  ],
};

export function Planned({ moduleKey }: { moduleKey: string }) {
  const { modules } = useAuth();
  const module = modules.find((m) => m.key === moduleKey);
  return (
    <>
      <PageHeader title={<span className="row">{module?.title ?? moduleKey} <Badge plain>Planned</Badge></span>} subtitle={module?.description} />
      <Card title="Coming in this module">
        <ul style={{ margin: 0, paddingLeft: 18 }} className="stack">
          {(PLANS[moduleKey] ?? []).map((item) => <li key={item}>{item}</li>)}
        </ul>
        <p className="small muted" style={{ marginTop: 14 }}>
          The <code>{module?.read_permission}</code> permission already exists, so roles can be prepared before the module ships.
        </p>
      </Card>
    </>
  );
}
