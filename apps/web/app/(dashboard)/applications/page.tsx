"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Button, Card, inputClass, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { ApplicationItem } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  prepared: "Prepared",
  submitted: "Submitted",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  status_unknown: "Status unknown",
  failed: "Failed",
};

const STATUS_STYLE: Record<string, string> = {
  submitted: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200",
  interviewing: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200",
  offer: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  rejected: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
  status_unknown: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200",
};

function day(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString() : "—";
}

export default function ApplicationsPage() {
  const { data, error, loading, sleeping, reload } = useApi<ApplicationItem[]>("/applications");
  const [focus] = useState(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("focus"),
  );

  const counts = (data ?? []).reduce<Record<string, number>>((acc, a) => ({ ...acc, [a.status]: (acc[a.status] ?? 0) + 1 }), {});

  return (
    <>
      <PageHeader
        title="Application Tracker"
        description="Every application, its status history and follow-ups. An application is shown as submitted only when you confirm it, or when a simulated submission ran on a synthetic job."
      />
      {loading && !data ? (
        <Loading sleeping={sleeping} />
      ) : error ? (
        <Alert kind="error">{error.message}</Alert>
      ) : !data?.length ? (
        <Alert>
          No applications yet. Open a job in{" "}
          <Link href="/jobs" className="underline">Job Discovery</Link> and use &quot;Add to tracker&quot;.
        </Alert>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted" data-testid="status-counts">
            {Object.entries(counts).map(([s, n]) => `${STATUS_LABEL[s] ?? s}: ${n}`).join(" · ")}
          </p>
          <div className="space-y-3">
            {data.map((a) => <ApplicationCard key={a.id} app={a} highlight={a.id === focus} onChange={reload} />)}
          </div>
        </>
      )}
    </>
  );
}

function ApplicationCard({ app, highlight, onChange }: { app: ApplicationItem; highlight: boolean; onChange: () => Promise<void> }) {
  const [next, setNext] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [notes, setNotes] = useState(app.notes ?? "");
  const [followUp, setFollowUp] = useState(app.follow_up_at ? app.follow_up_at.slice(0, 10) : "");
  const [history, setHistory] = useState<ApplicationItem["events"]>();
  const [msg, setMsg] = useState<string>();
  const needsConfirm = next === "submitted" && (app.status === "draft" || app.status === "prepared");

  async function call(fn: () => Promise<unknown>) {
    setMsg(undefined);
    try {
      await fn();
      setNext("");
      setConfirmed(false);
      setHistory(undefined);
      await onChange();
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Update failed");
    }
  }

  const patch = (body: Record<string, unknown>) => call(() => api(`/applications/${app.id}`, { method: "PATCH", body }));

  return (
    <Card className={highlight ? "ring-2 ring-brand" : ""}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">
            <Link href={`/jobs/${app.job_id}`} className="hover:underline">{app.job_title}</Link>
          </h3>
          <p className="text-sm text-muted">
            {app.company}
            {app.portal ? ` · via ${app.portal}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {app.job_is_synthetic && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
              Synthetic job
            </span>
          )}
          {app.is_simulated && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
              Simulated submission
            </span>
          )}
          <span data-testid="app-status" className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[app.status] ?? "bg-subtle"}`}>
            {STATUS_LABEL[app.status] ?? app.status}
          </span>
        </div>
      </div>

      <p className="mt-2 flex flex-wrap gap-x-4 text-xs text-muted">
        <span>Created {day(app.created_at)}</span>
        <span>Submitted {day(app.submitted_at)}{app.submitted_at && ` (${app.applied_via})`}</span>
        {app.external_reference && <span>Reference {app.external_reference}</span>}
        <span className={app.follow_up_due ? "font-medium text-red-700 dark:text-red-300" : ""}>
          Follow up {day(app.follow_up_at)}{app.follow_up_due && " — due"}
        </span>
      </p>

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <div>
          <label className="block text-xs font-medium" htmlFor={`next-${app.id}`}>Change status</label>
          <div className="mt-1 flex gap-2">
            <select id={`next-${app.id}`} className={inputClass} value={next} onChange={(e) => setNext(e.target.value)} disabled={!app.allowed_next.length}>
              <option value="">{app.allowed_next.length ? "Choose…" : "Final status"}</option>
              {app.allowed_next.map((s) => <option key={s} value={s}>{STATUS_LABEL[s] ?? s}</option>)}
            </select>
            <Button variant="secondary" disabled={!next || (needsConfirm && !confirmed)} onClick={() => patch({ status: next, confirm_submitted: confirmed })}>
              Update
            </Button>
          </div>
          {needsConfirm && (
            <label className="mt-1 flex items-start gap-1 text-xs">
              <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              I submitted this application on the portal myself.
            </label>
          )}
        </div>
        <div>
          <label className="block text-xs font-medium" htmlFor={`fu-${app.id}`}>Follow-up date</label>
          <div className="mt-1 flex gap-2">
            <input id={`fu-${app.id}`} type="date" className={inputClass} value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
            <Button variant="secondary" onClick={() => patch({ follow_up_at: followUp ? new Date(`${followUp}T09:00:00`).toISOString() : null })}>
              Save
            </Button>
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium" htmlFor={`notes-${app.id}`}>Notes</label>
          <div className="mt-1 flex gap-2">
            <input id={`notes-${app.id}`} className={inputClass} value={notes} onChange={(e) => setNotes(e.target.value)} />
            <Button variant="secondary" onClick={() => patch({ notes: notes || null })}>Save</Button>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {app.job_is_synthetic && app.portal === "mock" && (app.status === "draft" || app.status === "prepared") && (
          <Button variant="secondary" onClick={() => call(() => api(`/applications/${app.id}/simulate-submit`, { method: "POST" }))}>
            Run simulated submission
          </Button>
        )}
        {app.status === "status_unknown" && (
          <Button variant="secondary" onClick={() => call(() => api(`/applications/${app.id}/reconcile`, { method: "POST" }))}>
            Check status (reconcile)
          </Button>
        )}
        <Button
          variant="secondary"
          onClick={async () => setHistory(history ? undefined : (await api<ApplicationItem>(`/applications/${app.id}`)).events)}
        >
          {history ? "Hide history" : "History"}
        </Button>
        {(app.status === "draft" || app.status === "prepared") && (
          <Button variant="secondary" onClick={() => confirm("Delete this draft?") && call(() => api(`/applications/${app.id}`, { method: "DELETE" }))}>
            Delete draft
          </Button>
        )}
      </div>
      {msg && <div className="mt-2"><Alert kind="error">{msg}</Alert></div>}
      {history && (
        <ol className="mt-3 space-y-1 border-l border-line pl-3 text-xs">
          {history.map((e, i) => (
            <li key={i}>
              <span className="text-muted">{new Date(e.created_at).toLocaleString()}</span> · {e.event_type}
              {e.to_status && e.from_status !== e.to_status && ` → ${STATUS_LABEL[e.to_status] ?? e.to_status}`}
              {e.details.simulated === true && " (simulated)"}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
