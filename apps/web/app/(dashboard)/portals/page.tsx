"use client";

import { useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { Alert, Button, Card, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Capabilities, Portal } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const CAPS: [keyof Capabilities, string][] = [
  ["search_jobs", "Search jobs"],
  ["get_job_details", "Job details"],
  ["get_profile", "Read profile"],
  ["update_profile", "Update profile"],
  ["prepare_application", "Prepare application"],
  ["submit_application", "Submit application"],
  ["get_application_status", "Application status"],
];

export default function PortalsPage() {
  const { data, error, loading, sleeping, setData } = useApi<Portal[]>("/portals");
  const [busy, setBusy] = useState<string>();
  const [msg, setMsg] = useState<string>();

  async function check(code: string) {
    setBusy(code);
    setMsg(undefined);
    try {
      const updated = await api<Portal>(`/portals/${code}/check`, { method: "POST" });
      setData((data ?? []).map((p) => (p.code === code ? updated : p)));
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Check failed");
    } finally {
      setBusy(undefined);
    }
  }

  if (loading) return <Loading sleeping={sleeping} />;
  if (error || !data) return <Alert kind="error">{error?.message ?? "Failed to load"}</Alert>;

  return (
    <>
      <PageHeader
        title="Portal Connections"
        description="Real portals stay 'Unsupported' until their official integration options and terms are verified (Phase 5). No automated access is attempted before then."
      />
      {msg && <Alert kind="error">{msg}</Alert>}
      <div className="grid gap-4 lg:grid-cols-2">
        {data.map((p) => (
          <Card key={p.code}>
            <div className="mb-2 flex items-start justify-between gap-2">
              <div>
                <h2 className="font-semibold">{p.name}</h2>
                {p.base_url && !p.base_url.endsWith(".invalid") && (
                  <a href={p.base_url} target="_blank" rel="noopener noreferrer" className="text-xs text-brand hover:underline">
                    Open {p.name} manually ↗
                  </a>
                )}
              </div>
              <StatusBadge status={p.status} />
            </div>
            <p className="mb-3 text-sm text-muted">{p.capabilities.notes}</p>
            <ul className="mb-3 grid grid-cols-2 gap-1 text-xs">
              {CAPS.map(([k, label]) => (
                <li key={k} className={p.capabilities[k] ? "text-emerald-700 dark:text-emerald-300" : "text-muted"}>
                  {p.capabilities[k] ? "✓" : "–"} {label}
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between text-xs text-muted">
              <span>
                Last checked: {p.last_checked_at ? new Date(p.last_checked_at).toLocaleString() : "never"}
              </span>
              <Button variant="secondary" onClick={() => check(p.code)} disabled={busy === p.code}>
                {busy === p.code ? "Checking…" : "Check status"}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
