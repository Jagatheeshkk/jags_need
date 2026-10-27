"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, inputClass, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";

interface SetupStatus {
  setup_required: boolean;
  bootstrap_token_required: boolean;
}

export default function LoginPage() {
  const router = useRouter();
  const status = useApi<SetupStatus>("/auth/setup-status");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const setup = status.data?.setup_required ?? false;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      if (setup) {
        await api("/auth/setup", {
          method: "POST",
          body: {
            email,
            password,
            display_name: displayName,
            bootstrap_token: bootstrapToken || undefined,
          },
        });
      } else {
        await api("/auth/login", { method: "POST", body: { email, password } });
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <h1 className="mb-1 text-xl font-semibold">{setup ? "Create owner account" : "Sign in"}</h1>
        <p className="mb-5 text-sm text-muted">
          {setup
            ? "This is a single-user app. The first account created becomes the only owner."
            : "AI Job Agent — personal job search assistant."}
        </p>
        {status.loading ? (
          <Loading sleeping={status.sleeping} />
        ) : status.error ? (
          <Alert kind="error">{status.error.message}</Alert>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            {setup && (
              <Field label="Display name">
                <input className={inputClass} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              </Field>
            )}
            <Field label="Email">
              <input
                className={inputClass}
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Password" hint={setup ? "At least 12 characters." : undefined}>
              <input
                className={inputClass}
                type="password"
                autoComplete={setup ? "new-password" : "current-password"}
                required
                minLength={setup ? 12 : 1}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {setup && status.data?.bootstrap_token_required && (
              <Field label="Bootstrap token" hint="The BOOTSTRAP_TOKEN value configured on the server.">
                <input
                  className={inputClass}
                  type="password"
                  required
                  value={bootstrapToken}
                  onChange={(e) => setBootstrapToken(e.target.value)}
                />
              </Field>
            )}
            {error && <Alert kind="error">{error}</Alert>}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Please wait…" : setup ? "Create account" : "Sign in"}
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
