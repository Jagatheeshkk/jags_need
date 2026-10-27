"use client";

import { useState } from "react";
import { Alert, Button, Card, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { SyncPreview, SyncRun } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PORTALS = [
  ["linkedin", "LinkedIn"],
  ["indeed", "Indeed"],
  ["naukri", "Naukri"],
  ["instahyre", "Instahyre"],
  ["cutshort", "Cutshort"],
  ["mock", "Mock portal"],
] as const;

const STATUS_LABEL: Record<SyncRun["status"], string> = {
  manual_required: "Waiting for you",
  manual_completed: "Updated by you",
  pending: "Ready (simulated)",
  succeeded: "Simulated update done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function SyncPage() {
  const [portal, setPortal] = useState<string>("linkedin");
  const preview = useApi<SyncPreview>(`/profile-sync/${portal}/preview`);
  const history = useApi<SyncRun[]>("/profile-sync/runs");
  const [run, setRun] = useState<SyncRun>();
  const [confirmed, setConfirmed] = useState(false);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string }>();
  const [copied, setCopied] = useState<string>();

  async function call(fn: () => Promise<SyncRun>, ok: string) {
    setMsg(undefined);
    try {
      const r = await fn();
      setRun(r);
      setMsg({ kind: "success", text: ok });
      await Promise.all([preview.reload(), history.reload()]);
    } catch (e) {
      setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Failed" });
    }
  }

  const start = () => call(() => api<SyncRun>(`/profile-sync/${portal}/prepare`, { method: "POST" }), "Sync recorded. Follow the steps, then confirm.");
  const confirm = () =>
    run && call(() => api<SyncRun>(`/profile-sync/runs/${run.id}/confirm`, { method: "POST", body: { confirm_updated: true } }), "Marked as updated on the portal.");
  const simulate = () => run && call(() => api<SyncRun>(`/profile-sync/runs/${run.id}/run`, { method: "POST" }), "Simulated update done.");

  async function copy(key: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      setTimeout(() => setCopied(undefined), 1500);
    } catch {
      setCopied(undefined);
    }
  }

  const p = preview.data;
  const active = run && run.portal === portal ? run : undefined;

  return (
    <>
      <PageHeader
        title="Profile Sync"
        description="Portal-ready text from your master profile. No real portal permits automated profile updates, so you paste the changed sections yourself and confirm here; the history records what you did."
      />
      <div className="mb-4 flex flex-wrap gap-2" role="tablist">
        {PORTALS.map(([code, name]) => (
          <button
            key={code}
            role="tab"
            aria-selected={portal === code}
            onClick={() => { setPortal(code); setRun(undefined); setConfirmed(false); setMsg(undefined); }}
            className={`rounded-lg px-3 py-1.5 text-sm ${portal === code ? "bg-brand/10 font-medium text-brand" : "hover:bg-subtle"}`}
          >
            {name}
          </button>
        ))}
      </div>

      {preview.loading && !p ? (
        <Loading sleeping={preview.sleeping} />
      ) : preview.error || !p ? (
        <Alert kind="error">{preview.error?.message ?? "Failed to load"}</Alert>
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="space-y-3 xl:col-span-2">
            <p className="text-sm text-muted" data-testid="sync-summary">
              {p.last_synced_at
                ? `Last confirmed ${new Date(p.last_synced_at).toLocaleString()}. ${p.changed.length} section(s) changed since.`
                : "Never synced: every section is new."}
            </p>
            {p.fields.map((f) => (
              <Card key={f.key}>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">
                    {f.label}
                    {f.changed && (
                      <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                        Changed
                      </span>
                    )}
                  </p>
                  <span className="flex items-center gap-2 text-xs text-muted">
                    {f.chars} characters
                    <Button variant="secondary" disabled={!f.value} onClick={() => copy(f.key, f.value)}>
                      {copied === f.key ? "Copied" : "Copy"}
                    </Button>
                  </span>
                </div>
                <pre className="whitespace-pre-wrap rounded-lg bg-subtle p-3 text-sm font-sans">{f.value || "— empty in your profile —"}</pre>
              </Card>
            ))}
          </div>
          <div className="space-y-4">
            <Card title={`Update ${p.portal_name}`}>
              <ol className="mb-3 list-decimal space-y-1 pl-5 text-sm">
                {p.instructions.map((s) => <li key={s}>{s}</li>)}
              </ol>
              <p className="mb-3 text-xs text-muted">
                The portal&apos;s own editor enforces its length limits; character counts are shown for convenience.
              </p>
              {!active ? (
                <Button onClick={start}>{p.automated ? "Prepare simulated update" : "Start sync"}</Button>
              ) : active.status === "manual_required" ? (
                <div className="space-y-2">
                  <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                    I saved these changes on {p.portal_name} myself.
                  </label>
                  <Button disabled={!confirmed} onClick={confirm}>Confirm updated</Button>
                </div>
              ) : active.status === "pending" ? (
                <Button onClick={simulate}>Run simulated update</Button>
              ) : (
                <p className="text-sm">Status: {STATUS_LABEL[active.status]}</p>
              )}
              {msg && <div className="mt-3"><Alert kind={msg.kind}>{msg.text}</Alert></div>}
            </Card>
            <Card title="Sync history">
              {!history.data?.length ? (
                <p className="text-sm text-muted">No syncs yet.</p>
              ) : (
                <ul className="divide-y divide-line text-sm">
                  {history.data.map((h) => (
                    <li key={h.id} className="py-2">
                      <span className="font-medium capitalize">{h.portal}</span> · {STATUS_LABEL[h.status]}
                      <span className="block text-xs text-muted">
                        {new Date(h.finished_at ?? h.created_at).toLocaleString()}
                        {h.preview.changed?.length ? ` · ${h.preview.changed.length} section(s)` : ""}
                        {h.result.simulated === true ? " · simulated" : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
