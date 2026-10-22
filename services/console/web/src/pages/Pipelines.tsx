import { useEffect, useState } from "react";

import { api, projectPath, type Pipeline, type PipelineRun } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, Dialog, Empty, ErrorAlert, Loading, PageHeader, RunBadge, formatTime, relativeTime } from "../components/ui";
import { useAction, useApi } from "../hooks";

function BackfillDialog({ pipeline, onClose, onStarted }: { pipeline: string; onClose: () => void; onStarted: () => void }) {
  const { project, can } = useAuth();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [promote, setPromote] = useState(false);
  const run = useAction(async () => {
    await api(projectPath(project!, `/pipelines/${pipeline}/runs`), {
      method: "POST",
      body: { start: start || null, end: end || null, promote },
    });
    onStarted();
    onClose();
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Backfill · ${pipeline}`}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!start || run.pending} onClick={() => void run.run()}>Start backfill</button>
        </>
      }
    >
      <p className="muted small">
        Rebuilds the pipeline's dbt models for the range, then recomputes the affected feature views at their current version.
        Serving keeps the old values until the new version is promoted.
      </p>
      <div className="grid grid-2">
        <label>Start<input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} required /></label>
        <label>End <span className="hint">empty = now</span><input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      <label className="check">
        <input type="checkbox" checked={promote} disabled={!can("features.promote")} onChange={(e) => setPromote(e.target.checked)} />
        <span>Promote when finished {!can("features.promote") && <span className="muted">(needs features.promote)</span>}</span>
      </label>
      <ErrorAlert error={run.error} />
    </Dialog>
  );
}

function RunDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const { project } = useAuth();
  const run = useApi<PipelineRun>(projectPath(project!, `/pipelines/runs/${id}`), 3000);
  const r = run.data;
  return (
    <Dialog open wide onClose={onClose} title={<span className="row">Run {id} {r && <RunBadge status={r.status} />}</span>}>
      {!r ? <Loading /> : (
        <>
          <dl className="kv small">
            <dt>Pipeline</dt><dd>{r.pipeline}</dd>
            <dt>Triggered by</dt><dd>{r.triggered_by}</dd>
            <dt>Started</dt><dd>{formatTime(r.started_at)}</dd>
            <dt>Finished</dt><dd>{formatTime(r.finished_at)}</dd>
            <dt>Range</dt><dd>{r.args.start ? `${r.args.start} → ${r.args.end ?? "now"}${r.args.promote ? " (promote)" : ""}` : "incremental"}</dd>
          </dl>
          {Object.keys(r.result).length > 0 && <><h3>Result</h3><pre className="log">{JSON.stringify(r.result, null, 2)}</pre></>}
          <h3>Log</h3>
          <pre className="log">{r.log || "No log output captured."}</pre>
        </>
      )}
    </Dialog>
  );
}

export function Pipelines() {
  const { project, can } = useAuth();
  const pipelines = useApi<Pipeline[]>(projectPath(project!, "/pipelines"));
  const [poll, setPoll] = useState<number | undefined>(undefined);
  const runs = useApi<PipelineRun[]>(projectPath(project!, "/pipelines/runs"), poll);
  const anyRunning = (runs.data ?? []).some((r) => r.status === "running");
  useEffect(() => setPoll(anyRunning ? 2000 : undefined), [anyRunning]);
  const [backfill, setBackfill] = useState<string | null>(null);
  const [openRun, setOpenRun] = useState<string | null>(null);
  const start = useAction(async (name: string) => {
    const run = await api<PipelineRun>(projectPath(project!, `/pipelines/${name}/runs`), { method: "POST", body: {} });
    runs.reload();
    setOpenRun(run.id);
  });

  if (pipelines.loading && !pipelines.data) return <Loading />;
  return (
    <>
      <PageHeader title="Pipelines" subtitle="dbt build → feature materialisation, as scheduled runs or on demand." />
      <ErrorAlert error={pipelines.error ?? start.error} />
      <Card title="Pipelines" padded={false}>
        {(pipelines.data ?? []).length === 0 ? <Empty>This project defines no pipelines.</Empty> : (
          <table>
            <thead><tr><th>Name</th><th>dbt selection</th><th>Feature views</th><th>Schedule</th><th /></tr></thead>
            <tbody>
              {pipelines.data!.map((p) => (
                <tr key={p.name}>
                  <td><b>{p.name}</b></td>
                  <td className="mono small">{p.dbt_select ?? "—"}</td>
                  <td className="small">{Array.isArray(p.views) ? p.views.join(", ") : (p.views ?? "affected")}</td>
                  <td className="mono small">{p.schedule ?? <span className="muted">manual</span>}</td>
                  <td>
                    <div className="actions" style={{ justifyContent: "flex-end" }}>
                      {can("pipelines.run") && <button className="small" disabled={start.pending || anyRunning} onClick={() => void start.run(p.name)}>Run now</button>}
                      {can("pipelines.run") && can("features.backfill") && <button className="small" onClick={() => setBackfill(p.name)}>Backfill…</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="Recent runs" actions={anyRunning ? <Badge tone="accent">Live</Badge> : undefined} padded={false}>
        {(runs.data ?? []).length === 0 ? <Empty>No runs yet.</Empty> : (
          <table>
            <thead><tr><th>Run</th><th>Pipeline</th><th>Status</th><th>Kind</th><th>Triggered by</th><th>Started</th></tr></thead>
            <tbody>
              {runs.data!.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => setOpenRun(r.id)}>
                  <td className="mono small">{r.id}</td>
                  <td>{r.pipeline}</td>
                  <td><RunBadge status={r.status} /></td>
                  <td className="small">{r.args.start ? "backfill" : "incremental"}</td>
                  <td className="small">{r.triggered_by}</td>
                  <td className="small" title={formatTime(r.started_at)}>{relativeTime(r.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {backfill && <BackfillDialog pipeline={backfill} onClose={() => setBackfill(null)} onStarted={runs.reload} />}
      {openRun && <RunDialog id={openRun} onClose={() => setOpenRun(null)} />}
    </>
  );
}
