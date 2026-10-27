"use client";

import { useState, type FormEvent } from "react";
import { TagInput } from "@/components/TagInput";
import { Alert, Button, Card, Field, inputClass, PageHeader, PlannedFeature } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { PortalJob, WorkArrangement } from "@/lib/types";

function salary(j: PortalJob) {
  if (j.salary_min == null && j.salary_max == null) return "Salary not disclosed";
  const fmt = (n: number | null) => (n == null ? "?" : n.toLocaleString("en-IN"));
  return `${j.salary_currency ?? ""} ${fmt(j.salary_min)} – ${fmt(j.salary_max)}`;
}

export default function JobsPage() {
  const [titles, setTitles] = useState<string[]>(["QA Lead", "Test Manager"]);
  const [locations, setLocations] = useState<string[]>([]);
  const [arrangement, setArrangement] = useState<WorkArrangement>("any");
  const [jobs, setJobs] = useState<PortalJob[]>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function search(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      setJobs(
        await api<PortalJob[]>("/portals/mock/search", {
          method: "POST",
          body: { titles, locations, work_arrangement: arrangement, limit: 50 },
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Job Discovery"
        description="Phase 1 searches only the mock connector. Every result below is synthetic sample data, not a real opening."
      />
      <Card title="Search the mock portal">
        <form onSubmit={search} className="grid gap-4 md:grid-cols-3">
          <Field label="Titles / keywords">
            <TagInput label="Titles" value={titles} onChange={setTitles} />
          </Field>
          <Field label="Locations">
            <TagInput label="Locations" value={locations} onChange={setLocations} placeholder="e.g. Bengaluru, Remote" />
          </Field>
          <Field label="Work arrangement">
            <select className={inputClass} value={arrangement} onChange={(e) => setArrangement(e.target.value as WorkArrangement)}>
              <option value="any">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </Field>
          <div className="md:col-span-3">
            <Button type="submit" disabled={busy}>
              {busy ? "Searching…" : "Search"}
            </Button>
          </div>
        </form>
      </Card>
      <div className="mt-4 space-y-3">
        {error && <Alert kind="error">{error}</Alert>}
        {jobs && jobs.length === 0 && <Alert>No synthetic jobs match these filters.</Alert>}
        {jobs?.map((j) => (
          <Card key={j.external_id}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="font-semibold">{j.title}</h3>
                <p className="text-sm text-muted">
                  {j.company} · {j.location ?? "Location not stated"} · {j.work_arrangement ?? "arrangement unknown"}
                </p>
              </div>
              {j.is_synthetic && (
                <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                  Synthetic sample
                </span>
              )}
            </div>
            <p className="mt-2 text-sm">{j.description}</p>
            <p className="mt-2 text-xs text-muted">
              {salary(j)} · Experience {j.experience_min ?? "?"}–{j.experience_max ?? "?"} yrs · Skills: {j.skills.join(", ")}
            </p>
          </Card>
        ))}
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <PlannedFeature phase={2}>
          Job ingestion into your database, de-duplication, freshness indicators and the 0–100 match score with matched and
          missing skills and a plain-language explanation.
        </PlannedFeature>
        <PlannedFeature phase={5}>Searching real portals, only through integrations each portal officially permits.</PlannedFeature>
      </div>
    </>
  );
}
