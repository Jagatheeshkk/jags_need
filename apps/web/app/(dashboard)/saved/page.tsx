"use client";

import Link from "next/link";
import { JobCard } from "@/components/JobBits";
import { Alert, Loading, PageHeader } from "@/components/ui";
import type { JobList } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function SavedJobsPage() {
  const { data, error, loading, sleeping, reload } = useApi<JobList>("/jobs?saved_only=true&include_expired=true&limit=100");

  return (
    <>
      <PageHeader title="Saved Jobs" description="Jobs you saved, with up-to-date scores. Expired listings stay here, marked." />
      {loading && !data ? (
        <Loading sleeping={sleeping} />
      ) : error ? (
        <Alert kind="error">{error.message}</Alert>
      ) : !data || data.total === 0 ? (
        <Alert>
          Nothing saved yet. Use ☆ Save in{" "}
          <Link href="/jobs" className="underline">
            Job Discovery
          </Link>
          .
        </Alert>
      ) : (
        <div className="space-y-3">
          {data.items.map((j) => (
            <JobCard key={j.id} job={j} onSavedChange={(m) => !m.is_saved && void reload()} />
          ))}
        </div>
      )}
    </>
  );
}
