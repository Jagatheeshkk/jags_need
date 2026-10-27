"use client";

import Link from "next/link";
import { CompletenessMeter } from "@/components/CompletenessMeter";
import { StatusBadge } from "@/components/StatusBadge";
import { Alert, Card, Loading, PageHeader } from "@/components/ui";
import type { Overview } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <Card>
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums">{value}</p>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </Card>
  );
}

export default function OverviewPage() {
  const { data, error, loading, sleeping } = useApi<Overview>("/overview");

  if (loading) return <Loading sleeping={sleeping} />;
  if (error || !data) return <Alert kind="error">{error?.message ?? "Failed to load"}</Alert>;

  const totalApps = Object.values(data.applications).reduce((a, b) => a + b, 0);

  return (
    <>
      <PageHeader title="Overview" description="Every number here is counted from your own database." />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Real job listings" value={data.jobs.real} note="From verified portal integrations" />
        <Stat label="Synthetic sample jobs" value={data.jobs.synthetic} note="Mock connector, not real openings" />
        <Stat label="Applications tracked" value={totalApps} />
        <Stat label="Pending approvals" value={data.pending_approvals} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Profile">
          <CompletenessMeter completeness={data.profile_completeness} />
          <Link href="/profile" className="mt-4 inline-block text-sm text-brand hover:underline">
            Edit profile →
          </Link>
        </Card>
        <Card title="Portals">
          <ul className="divide-y divide-line">
            {data.portals.map((p) => (
              <li key={p.code} className="flex items-center justify-between py-2 text-sm">
                <span>{p.name}</span>
                <StatusBadge status={p.status} />
              </li>
            ))}
          </ul>
          <Link href="/portals" className="mt-3 inline-block text-sm text-brand hover:underline">
            Manage connections →
          </Link>
        </Card>
      </div>
      {data.unread_notifications > 0 && (
        <div className="mt-4">
          <Alert>
            You have {data.unread_notifications} unread notification(s).{" "}
            <Link href="/notifications" className="underline">
              View
            </Link>
          </Alert>
        </div>
      )}
    </>
  );
}
