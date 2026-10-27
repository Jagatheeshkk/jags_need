import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  // The shell reads the URL (active nav item, /jobs/[id] params); Cache Components needs a
  // Suspense boundary around URL-dependent client components on dynamic routes.
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted">Loading…</div>}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
