"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AutomationPreview, ResumeItem, TaskRun } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Alert, Button, Card, inputClass } from "./ui";

const ACTION_STYLE = {
  submit: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  approval: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  skip: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
} as const;

const ACTION_LABEL = { submit: "Would submit", approval: "Needs approval", skip: "Skip" } as const;

/** Dry-run preview and manual run of the rules engine. */
export function EnginePanel() {
  const [preview, setPreview] = useState<AutomationPreview>();
  const [run, setRun] = useState<TaskRun>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function go<T>(fn: () => Promise<T>, then: (v: T) => void) {
    setBusy(true);
    setError(undefined);
    try {
      then(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  const r = run?.result as (TaskRun["result"] & { state?: string; submitted?: number; approvals_created?: number; skipped?: number }) | undefined;

  return (
    <Card title="Engine">
      <p className="mb-3 text-sm text-muted">
        Preview shows what the saved rules would do now, without creating or submitting anything. Run applies them once.
        Runs also happen after each job refresh while automation is enabled and not paused.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy} onClick={() => go(() => api<AutomationPreview>("/automation/preview"), setPreview)}>
          Preview (dry run)
        </Button>
        <Button disabled={busy} onClick={() => go(() => api<TaskRun>("/automation/run", { method: "POST" }), (v) => { setRun(v); setPreview(undefined); })}>
          Run now
        </Button>
      </div>
      {error && <div className="mt-3"><Alert kind="error">{error}</Alert></div>}
      {run && r && (
        <div className="mt-3">
          <Alert kind={r.state === "ran" ? "success" : "info"}>
            {r.state === "paused" && "Global pause is on: nothing was done."}
            {r.state === "disabled" && "Automation is turned off: nothing was done."}
            {r.state === "ran" && (
              <>
                {r.submitted} simulated submission(s), {r.approvals_created} new approval request(s), {r.skipped} skipped.{" "}
                <Link href="/approvals" className="underline">Open Approval Queue</Link>
              </>
            )}
            {run.status === "failed" && ` Run failed: ${run.error}`}
          </Alert>
        </div>
      )}
      {preview && (
        <div className="mt-4">
          <p className="mb-2 text-sm" data-testid="preview-totals">
            {!preview.enabled || preview.global_pause ? "Currently off or paused — showing what would happen once enabled. " : ""}
            Would submit: <strong>{preview.totals.submit}</strong> · Needs approval: <strong>{preview.totals.approval}</strong> · Skip:{" "}
            <strong>{preview.totals.skip}</strong>
          </p>
          <ul className="divide-y divide-line text-sm">
            {preview.decisions.map((d) => (
              <li key={d.job_id} className="py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ACTION_STYLE[d.action]}`}>{ACTION_LABEL[d.action]}</span>
                  <Link href={`/jobs/${d.job_id}`} className="font-medium hover:underline">{d.title}</Link>
                  <span className="text-muted">· {d.company} · score {d.score ?? "n/a"}</span>
                </div>
                {d.reasons.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-xs text-muted">
                    {d.reasons.map((x) => <li key={x}>{x}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/** Role keyword -> resume used for automated applications to matching job titles. */
export function PreferredResumes({ value, onChange }: { value: Record<string, string>; onChange: (v: Record<string, string>) => void }) {
  const resumes = useApi<ResumeItem[]>("/resumes");
  const [keyword, setKeyword] = useState("");
  const [resumeId, setResumeId] = useState("");
  const options = resumes.data ?? [];
  const label = (id: string) => {
    const r = options.find((x) => x.id === id);
    return r ? `${r.label} v${r.version}` : "missing resume";
  };

  return (
    <div className="space-y-2 text-sm">
      {Object.entries(value).map(([k, id]) => (
        <div key={k} className="flex items-center justify-between gap-2">
          <span>
            Titles containing <strong>{k}</strong> → {label(id)}
          </span>
          <button type="button" className="text-xs text-muted hover:text-red-600" onClick={() => {
            const next = { ...value };
            delete next[k];
            onChange(next);
          }}>Remove</button>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <input aria-label="Role keyword" className={`${inputClass} w-40`} placeholder="e.g. Lead" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        <select aria-label="Resume for keyword" className={`${inputClass} w-56`} value={resumeId} onChange={(e) => setResumeId(e.target.value)}>
          <option value="">Choose resume…</option>
          {options.map((r) => <option key={r.id} value={r.id}>{r.label} v{r.version}</option>)}
        </select>
        <Button type="button" variant="secondary" disabled={!keyword.trim() || !resumeId} onClick={() => {
          onChange({ ...value, [keyword.trim()]: resumeId });
          setKeyword("");
          setResumeId("");
        }}>Add</Button>
      </div>
      <p className="text-xs text-muted">Without a match, automation generates a tailored resume from your profile.</p>
    </div>
  );
}
