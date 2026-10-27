"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Button, Card, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { AppNotification } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function NotificationsPage() {
  const { data, error, loading, sleeping, reload } = useApi<AppNotification[]>("/notifications");
  const [permission, setPermission] = useState<string>(() =>
    typeof window !== "undefined" && "Notification" in window ? Notification.permission : "unsupported",
  );

  async function markRead(id: string) {
    await api(`/notifications/${id}/read`, { method: "POST" });
    await reload();
  }
  async function markAll() {
    await api("/notifications/read-all", { method: "POST" });
    await reload();
  }
  async function enableBrowser() {
    if (!("Notification" in window)) return;
    setPermission(await Notification.requestPermission());
  }

  if (loading) return <Loading sleeping={sleeping} />;
  if (error || !data) return <Alert kind="error">{error?.message ?? "Failed to load"}</Alert>;

  return (
    <>
      <PageHeader
        title="Notifications"
        description="In-app notifications are the default channel. Email is disabled (no paid email service is used)."
        actions={
          <Button variant="secondary" onClick={markAll} disabled={!data.some((n) => !n.read_at)}>
            Mark all read
          </Button>
        }
      />
      <Card className="mb-4">
        <p className="text-sm">
          Browser notifications:{" "}
          <strong>{permission === "unsupported" ? "not supported in this browser" : permission}</strong>
        </p>
        {permission === "default" && (
          <Button variant="secondary" className="mt-2" onClick={enableBrowser}>
            Allow browser notifications
          </Button>
        )}
        <p className="mt-2 text-xs text-muted">
          Daily digest:{" "}
          <a href="/api/jobs/digest" className="text-brand hover:underline">
            download today&apos;s job digest (Markdown)
          </a>
          .
        </p>
      </Card>
      {data.length === 0 ? (
        <Alert>No notifications.</Alert>
      ) : (
        <ul className="space-y-2">
          {data.map((n) => (
            <li key={n.id}>
              <Card className={n.read_at ? "opacity-70" : ""}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{n.title}</p>
                    {n.body && <p className="text-sm text-muted">{n.body}</p>}
                    <p className="mt-1 text-xs text-muted">{new Date(n.created_at).toLocaleString()}</p>
                  </div>
                  <div className="flex gap-2">
                    {n.link?.startsWith("/") && (
                      <Link href={n.link} className="text-sm text-brand hover:underline">
                        Open
                      </Link>
                    )}
                    {!n.read_at && (
                      <Button variant="secondary" onClick={() => markRead(n.id)}>
                        Mark read
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
