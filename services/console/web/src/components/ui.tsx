import { useEffect, useRef, type ReactNode } from "react";

import type { Status } from "../api";

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export function Card({ title, actions, children, padded = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; padded?: boolean }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-header">
          <h2>{title}</h2>
          {actions && <div className="actions">{actions}</div>}
        </div>
      )}
      {padded ? <div className="card-body">{children}</div> : children}
    </section>
  );
}

type Tone = "ok" | "warn" | "danger" | "info" | "accent" | "neutral";

export function Badge({ tone = "neutral", children, plain }: { tone?: Tone; children: ReactNode; plain?: boolean }) {
  return <span className={`badge ${tone === "neutral" ? "" : tone} ${plain ? "plain" : ""}`}>{children}</span>;
}

export function ModuleStatus({ status }: { status: Status }) {
  if (status === "ready") return null;
  return <Badge tone={status === "preview" ? "info" : "neutral"} plain>{status === "preview" ? "Preview" : "Planned"}</Badge>;
}

const ROLLOUT: Record<string, [Tone, string]> = {
  unchanged: ["ok", "Live"],
  changed: ["warn", "Logic changed"],
  new: ["info", "Not materialised"],
};

export function RolloutBadge({ status }: { status?: string | null }) {
  if (!status) return <Badge plain>Computed on request</Badge>;
  const [tone, label] = ROLLOUT[status] ?? ["neutral", status];
  return <Badge tone={tone}>{label}</Badge>;
}

const RUN: Record<string, Tone> = { running: "accent", succeeded: "ok", failed: "danger" };

export function RunBadge({ status }: { status: string }) {
  return <Badge tone={RUN[status] ?? "neutral"}>{status}</Badge>;
}

export function ErrorAlert({ error }: { error?: Error | string | null }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : error.message;
  return <div className="alert error" role="alert">{message}</div>;
}

export function Loading() {
  return (
    <div className="center" aria-busy="true">
      <div className="spinner" />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Dialog({
  open, onClose, title, children, footer, wide,
}: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog ref={ref} className={wide ? "wide" : ""} onClose={onClose} onCancel={onClose}>
      {open && (
        <>
          <div className="dialog-header">
            <h2>{title}</h2>
            <button className="ghost small" onClick={onClose} aria-label="Close">✕</button>
          </div>
          <div className="dialog-body">{children}</div>
          {footer && <div className="dialog-footer">{footer}</div>}
        </>
      )}
    </dialog>
  );
}

export function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function relativeTime(value?: string | null): string {
  if (!value) return "never";
  const seconds = (Date.now() - new Date(value).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export function DataTable({ table }: { table: { columns: string[]; rows: unknown[][] } }) {
  if (!table.rows.length) return <Empty>No rows</Empty>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i}>
              {row.map((value, j) => (
                <td key={j} className={typeof value === "number" ? "num mono" : "mono"}>{formatValue(value)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
