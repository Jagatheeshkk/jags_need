"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import type { ComponentStatus, Freshness, JobMatch, JobSummary } from "@/lib/types";
import { Card } from "./ui";

export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-xs text-muted">Not scored</span>;
  const cls =
    score >= 75
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
      : score >= 50
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
        : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200";
  return (
    <span data-testid="score" className={`inline-flex min-w-12 justify-center rounded-lg px-2 py-1 text-sm font-semibold tabular-nums ${cls}`}>
      {Math.round(score)}
    </span>
  );
}

const FRESH: Record<Freshness, { label: string; cls: string }> = {
  new: { label: "New", cls: "text-emerald-700 dark:text-emerald-300" },
  fresh: { label: "Fresh", cls: "text-emerald-700 dark:text-emerald-300" },
  aging: { label: "Aging", cls: "text-amber-700 dark:text-amber-300" },
  stale: { label: "Stale (30+ days)", cls: "text-muted" },
  expired: { label: "Expired", cls: "text-red-700 dark:text-red-300" },
  unknown: { label: "Posting date unknown", cls: "text-muted" },
};

export function FreshnessTag({ freshness }: { freshness: Freshness }) {
  const f = FRESH[freshness];
  return <span className={`text-xs font-medium ${f.cls}`}>{f.label}</span>;
}

export const STATUS_STYLE: Record<ComponentStatus, string> = {
  match: "text-emerald-700 dark:text-emerald-300",
  partial: "text-amber-700 dark:text-amber-300",
  mismatch: "text-red-700 dark:text-red-300",
  unknown: "text-muted",
};

export function EligibilityTag({ match }: { match: JobMatch | null }) {
  if (!match) return null;
  const s = match.eligibility.status;
  if (s === "eligible") return null;
  return (
    <span
      title={match.eligibility.reasons.join(" ")}
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        s === "ineligible"
          ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200"
          : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200"
      }`}
    >
      {s === "ineligible" ? "Not eligible" : "Eligibility unknown"}
    </span>
  );
}

export function SyntheticTag() {
  return (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
      Synthetic sample
    </span>
  );
}

export function salaryText(j: Pick<JobSummary, "salary_min" | "salary_max" | "salary_currency">) {
  if (j.salary_min == null && j.salary_max == null) return "Salary not disclosed";
  const fmt = (n: number | null) => (n == null ? "?" : n.toLocaleString("en-IN"));
  return `${j.salary_currency ?? ""} ${fmt(j.salary_min)} – ${fmt(j.salary_max)}`.trim();
}

export function SaveButton({ job, onChange }: { job: JobSummary; onChange?: (m: JobMatch) => void }) {
  const [saved, setSaved] = useState(job.match?.is_saved ?? false);
  const [busy, setBusy] = useState(false);
  async function toggle() {
    setBusy(true);
    try {
      const m = await api<JobMatch>(`/jobs/${job.id}/saved`, { method: "PUT", body: { saved: !saved } });
      setSaved(m.is_saved);
      onChange?.(m);
    } finally {
      setBusy(false);
    }
  }
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={saved}
      className={`rounded-lg border px-3 py-1.5 text-sm ${saved ? "border-brand bg-brand/10 text-brand" : "border-line hover:bg-subtle"}`}
    >
      {saved ? "★ Saved" : "☆ Save"}
    </button>
  );
}

export function JobCard({ job, onSavedChange }: { job: JobSummary; onSavedChange?: (m: JobMatch) => void }) {
  const m = job.match;
  return (
    <Card>
      <div className="flex gap-4">
        <ScoreBadge score={m?.score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="font-semibold">
                <Link href={`/jobs/${job.id}`} className="hover:underline">
                  {job.title}
                </Link>
              </h3>
              <p className="text-sm text-muted">
                {job.company} · {job.location ?? "Location not stated"} · {job.work_arrangement ?? "arrangement not stated"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {job.is_synthetic && <SyntheticTag />}
              <EligibilityTag match={m} />
              <SaveButton job={job} onChange={onSavedChange} />
            </div>
          </div>
          <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
            <FreshnessTag freshness={job.freshness} />
            <span>{salaryText(job)}</span>
            <span>
              Experience {job.experience_min ?? "?"}–{job.experience_max ?? "?"} yrs
            </span>
            {job.source_count > 1 && <span>Seen on {job.source_count} sources (merged duplicates)</span>}
          </p>
          {m && (m.matched_skills.length > 0 || m.missing_skills.length > 0) && (
            <p className="mt-2 text-xs">
              {m.matched_skills.length > 0 && (
                <span className="text-emerald-700 dark:text-emerald-300">✓ {m.matched_skills.join(", ")}</span>
              )}
              {m.missing_skills.length > 0 && (
                <span className="ml-2 text-muted">Missing: {m.missing_skills.join(", ")}</span>
              )}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
