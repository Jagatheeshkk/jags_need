"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, inputClass, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Account security, your data, and the audit trail." />
      <div className="grid gap-4 lg:grid-cols-2">
        <ChangePassword />
        <Sessions />
        <ExportData />
        <DeleteData />
        <AuditTrail />
      </div>
    </>
  );
}

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string }>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/change-password", { method: "POST", body: { current_password: current, new_password: next } });
      setMsg({ kind: "success", text: "Password changed. Other sessions were signed out." });
      setCurrent("");
      setNext("");
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof ApiError ? err.message : "Failed" });
    }
  }

  return (
    <Card title="Change password">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Current password">
          <input className={inputClass} type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password" hint="At least 12 characters.">
          <input className={inputClass} type="password" autoComplete="new-password" minLength={12} required value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
        <Button type="submit">Change password</Button>
      </form>
    </Card>
  );
}

function Sessions() {
  const router = useRouter();
  return (
    <Card title="Sessions">
      <p className="mb-3 text-sm text-muted">Sign out everywhere, including this browser and any other device.</p>
      <Button
        variant="secondary"
        onClick={async () => {
          await api("/auth/logout-all", { method: "POST" });
          router.replace("/login");
        }}
      >
        Sign out of all sessions
      </Button>
    </Card>
  );
}

function ExportData() {
  return (
    <Card title="Export your data">
      <p className="mb-3 text-sm text-muted">
        Download everything stored about you as JSON (profile, rules, applications, notifications, audit log). Keep this as a
        backup in addition to database dumps.
      </p>
      <a href="/api/data/export" className="inline-block rounded-lg border border-line px-3.5 py-2 text-sm font-medium hover:bg-subtle">
        Download export
      </a>
    </Card>
  );
}

function DeleteData() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState<string>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/data/delete", { method: "POST", body: { password, confirm: confirmText } });
      router.replace("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    }
  }

  return (
    <Card title="Delete all personal data">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-muted">
          Permanently deletes your account, profile, rules, applications and audit log. Export first if you want a copy.
        </p>
        <Field label='Type "DELETE MY DATA" to confirm'>
          <input className={inputClass} value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
        </Field>
        <Field label="Password">
          <input className={inputClass} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {error && <Alert kind="error">{error}</Alert>}
        <Button type="submit" variant="danger" disabled={confirmText !== "DELETE MY DATA" || !password}>
          Delete everything
        </Button>
      </form>
    </Card>
  );
}

function AuditTrail() {
  const { data, error } = useApi<AuditEntry[]>("/audit?limit=25");
  return (
    <Card title="Recent activity (audit log)" className="lg:col-span-2">
      {error && <Alert kind="error">{error.message}</Alert>}
      <ul className="divide-y divide-line text-sm">
        {data?.map((a) => (
          <li key={a.id} className="flex flex-wrap justify-between gap-2 py-2">
            <span className="font-mono text-xs">{a.action}</span>
            <span className="text-xs text-muted">
              {Array.isArray(a.details.fields) ? `fields: ${(a.details.fields as string[]).join(", ")} · ` : ""}
              {new Date(a.created_at).toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
