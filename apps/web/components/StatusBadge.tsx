import type { ConnectionStatus } from "@/lib/types";

const STYLES: Record<ConnectionStatus, { label: string; className: string }> = {
  connected: { label: "Connected", className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200" },
  succeeded: { label: "Successfully completed", className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200" },
  not_connected: { label: "Not connected", className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200" },
  unsupported: { label: "Unsupported", className: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200" },
  needs_user_action: { label: "Needs user action", className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200" },
  sleeping: { label: "Sleeping / temporarily unavailable", className: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200" },
  rate_limited: { label: "Rate limited", className: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200" },
  failed: { label: "Failed", className: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200" },
};

export function StatusBadge({ status }: { status: ConnectionStatus }) {
  const s = STYLES[status] ?? STYLES.failed;
  return (
    <span
      data-testid="status-badge"
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${s.className}`}
    >
      {s.label}
    </span>
  );
}
