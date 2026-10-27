"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  EligibilityTag,
  FreshnessTag,
  SaveButton,
  salaryText,
  ScoreBadge,
  STATUS_STYLE,
  SyntheticTag,
} from "@/components/JobBits";
import { Alert, Button, Card, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { JobDetail, JobMatch } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const LABELS: Record<string, string> = {
  skills_experience: "Skills and experience",
  role_responsibilities: "Role responsibilities",
  domain_experience: "Domain experience",
  location_work_arrangement: "Location and work arrangement",
  compensation_fit: "Compensation fit",
};

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: job, error, loading, sleeping, setData } = useApi<JobDetail>(`/jobs/${id}`);
  const [feedbackMsg, setFeedbackMsg] = useState<string>();

  async function feedback(value: JobMatch["feedback"]) {
    if (!job) return;
    const m = await api<JobMatch>(`/jobs/${job.id}/feedback`, { method: "PUT", body: { feedback: value } });
    setData({ ...job, match: m });
    setFeedbackMsg("Thanks — feedback saved. It is kept for tuning the weights later.");
  }

  if (loading) return <Loading sleeping={sleeping} />;
  if (error || !job) return <Alert kind="error">{error?.message ?? "Job not found"}</Alert>;
  const m = job.match;

  return (
    <>
      <Link href="/jobs" className="text-sm text-brand hover:underline">
        ← Job Discovery
      </Link>
      <div className="mt-2">
        <PageHeader
          title={job.title}
          description={`${job.company} · ${job.location ?? "Location not stated"} · ${job.work_arrangement ?? "arrangement not stated"}`}
          actions={<SaveButton job={job} onChange={(mm) => setData({ ...job, match: mm })} />}
        />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <ScoreBadge score={m?.score} />
        {job.is_synthetic && <SyntheticTag />}
        <EligibilityTag match={m} />
        <FreshnessTag freshness={job.freshness} />
        <span className="text-sm text-muted">{salaryText(job)}</span>
      </div>
      {job.is_synthetic && (
        <div className="mb-4">
          <Alert kind="warn">This is synthetic sample data from the mock connector, not a real opening.</Alert>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Why this score">
            {m ? (
              <>
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-muted">
                    <tr>
                      <th className="py-1">Component</th>
                      <th className="py-1">Weight</th>
                      <th className="py-1">Result</th>
                      <th className="py-1">Detail</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {Object.entries(m.components).map(([k, c]) => (
                      <tr key={k}>
                        <td className="py-2 pr-2 font-medium">{LABELS[k] ?? k}</td>
                        <td className="py-2 pr-2 tabular-nums">{c.weight}%</td>
                        <td className={`py-2 pr-2 font-medium ${STATUS_STYLE[c.status]}`}>{c.status}</td>
                        <td className="py-2 text-muted">{c.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 text-xs text-muted">
                  &quot;unknown&quot; means data was missing; it counts as neutral (half credit), never as a confirmed match.
                </p>
                {m.eligibility.status !== "eligible" && (
                  <div className="mt-3">
                    <Alert kind={m.eligibility.status === "ineligible" ? "error" : "info"}>
                      Eligibility {m.eligibility.status}: {m.eligibility.reasons.join(" ")}
                    </Alert>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">Not scored yet.</p>
            )}
          </Card>
          <Card title="Description">
            {/* Third-party text, rendered as plain text only. */}
            <p className="whitespace-pre-wrap text-sm">{job.description ?? "No description provided."}</p>
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Skills">
            <p className="text-xs font-medium">Matched</p>
            <p className="mb-2 text-sm text-emerald-700 dark:text-emerald-300">{m?.matched_skills.join(", ") || "—"}</p>
            <p className="text-xs font-medium">Listed but not in your profile</p>
            <p className="text-sm text-muted">{m?.missing_skills.join(", ") || "—"}</p>
          </Card>
          <Card title="Was this a good match?">
            <div className="flex gap-2">
              <Button variant={m?.feedback === "good_match" ? "primary" : "secondary"} onClick={() => feedback("good_match")}>
                Good match
              </Button>
              <Button variant={m?.feedback === "poor_match" ? "primary" : "secondary"} onClick={() => feedback("poor_match")}>
                Poor match
              </Button>
            </div>
            {feedbackMsg && <p className="mt-2 text-xs text-muted">{feedbackMsg}</p>}
          </Card>
          <Card title="Sources">
            <ul className="space-y-1 text-sm">
              {job.sources.map((s) => (
                <li key={`${s.portal}-${s.external_id}`}>
                  <span className="font-mono text-xs">{s.portal}</span> · {s.external_id}
                  <span className="block text-xs text-muted">Fetched {new Date(s.fetched_at).toLocaleString()}</span>
                </li>
              ))}
            </ul>
            {job.sources.length > 1 && <p className="mt-2 text-xs text-muted">Duplicates merged into this one listing.</p>}
          </Card>
          <Card title="Apply">
            <p className="text-sm text-muted">Application preparation and tracking arrive in Phase 3.</p>
          </Card>
        </div>
      </div>
    </>
  );
}
