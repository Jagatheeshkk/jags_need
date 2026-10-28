"use client";

import { Alert, Button, Card, Loading, PageHeader } from "@/components/ui";
import type { ReadinessReport, StorageUsage } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const STATUS_STYLE = {
  ok: "text-emerald-700 dark:text-emerald-300",
  info: "text-sky-700 dark:text-sky-300",
  warn: "text-amber-700 dark:text-amber-300",
  fail: "text-red-700 dark:text-red-300",
};

// Summary of docs/free-tier-audit.md. Limits change: re-verify on the provider's pricing page.
const LIMITS = [
  { service: "Vercel Hobby (frontend)", limit: "Personal, non-commercial use only. No billing on Hobby: a feature that exceeds its monthly limit pauses (up to 30 days) instead of charging." },
  { service: "Render Free web service (API)", limit: "512 MB RAM, 0.1 CPU. Spins down after 15 min without traffic; waking takes about a minute. 750 free instance hours per workspace per month, then suspended until next month." },
  { service: "Neon Free (PostgreSQL)", limit: "1 GB storage and 100 CU-hours per project per month. Compute suspends after 5 min idle. Over a limit, compute or writes pause; data is not deleted." },
  { service: "GitHub Free + Actions", limit: "Free for public repositories; 2,000 minutes per month for private ones. Without a payment method, usage stops at the quota." },
  { service: "AI engine", limit: "Rule-based by default (no API key, no cost). Optional local Ollama on your own machine." },
];

export default function HealthPage() {
  const health = useApi<{ status: string; database: string; time: string }>("/health");
  const readiness = useApi<ReadinessReport>("/settings/readiness");
  const usage = useApi<StorageUsage>("/settings/usage");

  return (
    <>
      <PageHeader
        title="Free-Tier Usage & Health"
        description="Live checks from the backend, plus the documented free-plan limits this deployment depends on."
        actions={
          <Button variant="secondary" onClick={() => Promise.all([health.reload(), readiness.reload()])}>
            Refresh
          </Button>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Service health">
          {health.loading ? (
            <Loading sleeping={health.sleeping} />
          ) : health.error ? (
            <Alert kind="warn">{health.error.message}</Alert>
          ) : (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-muted">API</dt>
              <dd>{health.data?.status}</dd>
              <dt className="text-muted">Database</dt>
              <dd>{health.data?.database}</dd>
              <dt className="text-muted">Server time (UTC)</dt>
              <dd>{health.data?.time}</dd>
            </dl>
          )}
        </Card>
        <Card title="Deployment readiness">
          {readiness.loading ? (
            <Loading sleeping={readiness.sleeping} />
          ) : readiness.error || !readiness.data ? (
            <Alert kind="error">{readiness.error?.message}</Alert>
          ) : (
            <>
              <p className="mb-2 text-sm">
                Paid dependencies:{" "}
                <strong>{readiness.data.paid_dependencies.length === 0 ? "none" : readiness.data.paid_dependencies.join(", ")}</strong>
              </p>
              <ul className="space-y-2 text-sm">
                {readiness.data.checks.map((c) => (
                  <li key={c.name}>
                    <span className={`font-medium uppercase ${STATUS_STYLE[c.status]}`}>{c.status}</span>{" "}
                    <span className="font-mono text-xs">{c.name}</span>
                    <p className="text-muted">{c.detail}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
        <Card title="Database storage" className="lg:col-span-2">
          {usage.loading ? (
            <Loading sleeping={usage.sleeping} />
          ) : usage.error || !usage.data ? (
            <Alert kind="error">{usage.error?.message}</Alert>
          ) : (
            <>
              {usage.data.used_percent !== null && (
                <div
                  className="mb-2 h-2 w-full overflow-hidden rounded-full bg-subtle"
                  role="progressbar"
                  aria-label="Database storage used"
                  aria-valuenow={usage.data.used_percent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className={`h-full ${usage.data.status === "ok" ? "bg-emerald-500" : usage.data.status === "warn" ? "bg-amber-500" : "bg-red-500"}`}
                    style={{ width: `${Math.min(100, usage.data.used_percent)}%` }}
                  />
                </div>
              )}
              <p className={`text-sm ${STATUS_STYLE[usage.data.status]}`} data-testid="storage-detail">{usage.data.detail}</p>
              <p className="mt-2 text-xs text-muted">
                Uploaded resumes: {(usage.data.uploaded_resume_bytes / 1024).toFixed(0)} KB ·{" "}
                {Object.entries(usage.data.row_counts).map(([k, v]) => `${k} ${v}`).join(" · ")}
              </p>
            </>
          )}
        </Card>
        <Card title="Free-plan limits relied on" className="lg:col-span-2">
          <table className="w-full text-left text-sm">
            <tbody className="divide-y divide-line">
              {LIMITS.map((l) => (
                <tr key={l.service}>
                  <th className="py-2 pr-4 align-top font-medium">{l.service}</th>
                  <td className="py-2 text-muted">{l.limit}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">
            Providers can change free plans at any time. See docs/free-tier-audit.md for sources and verification dates.
          </p>
        </Card>
      </div>
    </>
  );
}
