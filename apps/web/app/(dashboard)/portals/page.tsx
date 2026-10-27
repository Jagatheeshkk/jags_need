"use client";

import Link from "next/link";
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

const WORKFLOWS: Record<string, string> = {
  search_link: "Open the portal's own search in your browser",
  manual_job_capture: "Add listings you find there (Job Discovery → Add a job you found)",
  profile_content: "Copy portal-ready profile text (Profile Sync)",
  manual_application_tracking: "Apply yourself, then confirm it in the Application Tracker",
};

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
        description="Each portal's official terms and developer documentation were checked. None permits automated access for job seekers, so real portals work through manual workflows only; the server never contacts them."
      />
      {msg && <div className="mb-4"><Alert kind="error">{msg}</Alert></div>}
      <div className="grid gap-4 lg:grid-cols-2">
        {data.map((p) => {
          const caps = p.capabilities;
          const manual = caps.mode === "manual";
          return (
            <Card key={p.code}>
              <div className="mb-2 flex items-start justify-between gap-2">
                <div>
                  <h2 className="font-semibold">{p.name}</h2>
                  <p className="text-xs text-muted">
                    {manual ? "Manual workflows only" : caps.mode === "mock" ? "Synthetic test portal" : caps.mode}
                    {caps.verified_on && ` · checked ${caps.verified_on}`}
                    {caps.verification === "terms_unavailable" && " · terms could not be retrieved"}
                  </p>
                </div>
                <StatusBadge status={p.status} />
              </div>
              <p className="mb-3 text-sm text-muted">{caps.notes}</p>

              <p className="mb-1 text-xs font-medium">Automated operations</p>
              <ul className="mb-3 grid grid-cols-2 gap-1 text-xs">
                {CAPS.map(([k, label]) => (
                  <li key={k} className={caps[k] ? "text-emerald-700 dark:text-emerald-300" : "text-muted"}>
                    {caps[k] ? "✓" : "–"} {label}
                  </li>
                ))}
              </ul>

              {manual && (
                <>
                  <p className="mb-1 text-xs font-medium">What you can do</p>
                  <ul className="mb-3 list-disc pl-5 text-xs">
                    {caps.manual_workflows.map((w) => <li key={w}>{WORKFLOWS[w] ?? w}</li>)}
                  </ul>
                  <details className="mb-3 text-xs">
                    <summary className="cursor-pointer font-medium">Evidence ({caps.evidence.length})</summary>
                    <ul className="mt-2 space-y-2">
                      {caps.evidence.map((e, i) => (
                        <li key={i}>
                          <a href={e.url} target="_blank" rel="noopener noreferrer" className="break-all text-brand hover:underline">{e.url}</a>
                          <p className="text-muted">{e.finding}</p>
                        </li>
                      ))}
                    </ul>
                  </details>
                </>
              )}

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                <span>Last checked: {p.last_checked_at ? new Date(p.last_checked_at).toLocaleString() : "never"}</span>
                <div className="flex gap-2">
                  {manual && (
                    <>
                      <SearchLink code={p.code} name={p.name} />
                      <Link href="/sync" className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium hover:bg-subtle">
                        Profile text
                      </Link>
                    </>
                  )}
                  {!manual && (
                    <Button variant="secondary" onClick={() => check(p.code)} disabled={busy === p.code}>
                      {busy === p.code ? "Checking…" : "Check status"}
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </>
  );
}

/** Link to the portal's own search for your preferred role and location; your browser opens it. */
function SearchLink({ code, name }: { code: string; name: string }) {
  const { data } = useApi<{ url: string; keywords: string; location: string | null }>(`/portals/${code}/search-link`);
  if (!data) return null;
  return (
    <a
      href={data.url}
      target="_blank"
      rel="noopener noreferrer"
      title={`Search ${name} for "${data.keywords}"${data.location ? ` in ${data.location}` : ""}`}
      className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium hover:bg-subtle"
    >
      Search on {name} ↗
    </a>
  );
}
