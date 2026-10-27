"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { JobCard } from "@/components/JobBits";
import { Alert, Button, Card, Field, inputClass, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { DEFAULT_FILTERS as DEFAULTS, type Filters, toQuery } from "@/lib/jobs";
import type { JobList, TaskRun } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function RunSummary({ run }: { run: TaskRun }) {
  const r = run.result;
  const when = new Date(run.finished_at ?? run.created_at).toLocaleString();
  if (run.status !== "succeeded") {
    return (
      <Alert kind={run.status === "running" ? "info" : "warn"}>
        Last refresh {run.status} ({when}). {run.error}
      </Alert>
    );
  }
  return (
    <p className="text-xs text-muted">
      Last refresh {when}: {r.fetched ?? 0} fetched, {r.created ?? 0} new, {r.updated ?? 0} updated, {r.merged ?? 0} merged as
      duplicates, {r.expired ?? 0} expired.
      {r.portals_searched?.length ? ` Searched: ${r.portals_searched.join(", ")}.` : ""}
      {r.portals_skipped && Object.keys(r.portals_skipped).length > 0
        ? ` Not searched (integration not verified): ${Object.keys(r.portals_skipped).join(", ")}.`
        : ""}
      {r.portal_errors && Object.keys(r.portal_errors).length > 0
        ? ` Errors: ${Object.entries(r.portal_errors).map(([k, v]) => `${k} (${v})`).join("; ")}.`
        : ""}
    </p>
  );
}

export default function JobsPage() {
  const [draft, setDraft] = useState<Filters>(DEFAULTS);
  const [applied, setApplied] = useState<Filters>(DEFAULTS);
  const list = useApi<JobList>(`/jobs?${toQuery(applied, { limit: "100" })}`);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string>();
  const autoTried = useRef(false);
  const { reload } = list;

  async function refresh(onlyIfDue = false) {
    setRefreshing(true);
    setError(undefined);
    try {
      await api<TaskRun>(`/jobs/refresh${onlyIfDue ? "?only_if_due=true" : ""}`, { method: "POST" });
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  // Free hosting cannot run a timer while asleep, so the schedule is checked when this page opens.
  useEffect(() => {
    if (list.data?.refresh_due && !autoTried.current) {
      autoTried.current = true;
      void refresh(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.data?.refresh_due]);

  function apply(e: FormEvent) {
    e.preventDefault();
    setApplied(draft);
  }
  const set = (k: keyof Filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft({ ...draft, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });

  return (
    <>
      <PageHeader
        title="Job Discovery"
        description="Jobs collected from permitted sources, de-duplicated and scored against your profile by the rule-based engine."
        actions={
          <>
            <a href="/api/jobs/digest" className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium hover:bg-subtle">
              Download digest
            </a>
            <Button onClick={() => refresh(false)} disabled={refreshing}>
              {refreshing ? "Refreshing…" : "Refresh now"}
            </Button>
          </>
        }
      />
      <Alert kind="warn">
        Only the mock connector is active, so every job here is synthetic sample data. Real portals stay off until their
        permitted integration options are verified (Phase 5).
      </Alert>
      <div className="mt-3 space-y-2">
        {list.data?.last_refresh && <RunSummary run={list.data.last_refresh} />}
        {error && <Alert kind="error">{error}</Alert>}
      </div>

      <Card className="mt-4">
        <form onSubmit={apply} className="grid gap-3 md:grid-cols-4">
          <Field label="Search">
            <input className={inputClass} value={draft.q} onChange={set("q")} placeholder="Title, company, text" />
          </Field>
          <Field label="Role contains">
            <input className={inputClass} value={draft.role} onChange={set("role")} placeholder="e.g. lead" />
          </Field>
          <Field label="Location">
            <input className={inputClass} value={draft.location} onChange={set("location")} placeholder="e.g. Bengaluru, remote" />
          </Field>
          <Field label="Work arrangement">
            <select className={inputClass} value={draft.work_arrangement} onChange={set("work_arrangement")}>
              <option value="">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </Field>
          <Field label="Minimum score">
            <input className={inputClass} type="number" min={0} max={100} value={draft.min_score} onChange={set("min_score")} />
          </Field>
          <Field label="Minimum salary" hint="Jobs with undisclosed salary are kept.">
            <input className={inputClass} type="number" min={0} value={draft.min_salary} onChange={set("min_salary")} />
          </Field>
          <Field label="Sort by">
            <select className={inputClass} value={draft.sort} onChange={set("sort")}>
              <option value="score">Best match</option>
              <option value="newest">Newest</option>
            </select>
          </Field>
          <div className="space-y-1 pt-6 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={draft.eligible_only} onChange={set("eligible_only")} />
              Eligible only
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={draft.include_expired} onChange={set("include_expired")} />
              Include expired
            </label>
          </div>
          <div className="flex gap-2 md:col-span-4">
            <Button type="submit">Apply filters</Button>
            <Button type="button" variant="secondary" onClick={() => { setDraft(DEFAULTS); setApplied(DEFAULTS); }}>
              Reset
            </Button>
          </div>
        </form>
      </Card>

      <div className="mt-4 space-y-3">
        {list.loading && !list.data ? (
          <Loading sleeping={list.sleeping} />
        ) : list.error ? (
          <Alert kind="error">{list.error.message}</Alert>
        ) : list.data && list.data.total === 0 ? (
          <Alert>
            {list.data.last_refresh
              ? "No jobs match these filters. Try widening them, or add preferred roles and locations in My Profile."
              : "No jobs yet. Click Refresh now to collect jobs."}
          </Alert>
        ) : (
          <>
            <p className="text-sm text-muted" data-testid="job-total">
              {list.data?.total} job(s)
            </p>
            {list.data?.items.map((j) => <JobCard key={j.id} job={j} />)}
          </>
        )}
      </div>
    </>
  );
}
