"use client";

import { useState, type FormEvent } from "react";
import { TagInput } from "@/components/TagInput";
import { EnginePanel, PreferredResumes } from "@/components/AutomationPanels";
import { Alert, Button, Card, Field, inputClass, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { AutomationRules } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const WEIGHT_LABELS: Record<string, string> = {
  skills_experience: "Skills and experience",
  role_responsibilities: "Role responsibilities",
  domain_experience: "Domain experience",
  location_work_arrangement: "Location and work arrangement",
  compensation_fit: "Compensation fit",
};

export default function AutomationPage() {
  const { data, error, loading, sleeping } = useApi<AutomationRules>("/settings/automation");
  if (loading) return <Loading sleeping={sleeping} />;
  if (error || !data) return <Alert kind="error">{error?.message ?? "Failed to load"}</Alert>;
  return <RulesForm initial={data} />;
}

function RulesForm({ initial }: { initial: AutomationRules }) {
  const [r, setR] = useState<AutomationRules>(initial);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string }>();
  const [busy, setBusy] = useState(false);
  const weightTotal = Object.values(r.score_weights).reduce((a, b) => a + b, 0);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(undefined);
    try {
      const { updated_at: _u, ...body } = r;
      setR(await api<AutomationRules>("/settings/automation", { method: "PUT", body }));
      setMsg({ kind: "success", text: "Rules saved" });
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof ApiError ? err.message : "Save failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Automation Rules"
        description="Automation is off and paused by default. Submissions happen only where the portal permits it, the job passes every rule and eligibility check, and no answer needs your confirmation. Everything else goes to the Approval Queue."
      />
      <Alert kind="warn">
        Only the mock connector can submit today, so every automated submission is simulated and labelled as such. Real portals
        stay manual until Phase 5 verifies what each one permits.
      </Alert>
      <div className="mt-4">
        <EnginePanel />
      </div>
      <form onSubmit={save} className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Master switches">
          <label className="mb-2 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={r.enabled} onChange={(e) => setR({ ...r, enabled: e.target.checked })} />
            Automation enabled
          </label>
          <label className="mb-4 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={r.global_pause} onChange={(e) => setR({ ...r, global_pause: e.target.checked })} />
            Global pause (overrides everything)
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Minimum match score">
              <input className={inputClass} type="number" min={0} max={100} value={r.min_match_score}
                onChange={(e) => setR({ ...r, min_match_score: Number(e.target.value) })} />
            </Field>
            <Field label="Max applications per day">
              <input className={inputClass} type="number" min={0} max={50} value={r.max_applications_per_day}
                onChange={(e) => setR({ ...r, max_applications_per_day: Number(e.target.value) })} />
            </Field>
            <Field label="Minimum salary">
              <input className={inputClass} type="number" min={0} value={r.min_salary ?? ""}
                onChange={(e) => setR({ ...r, min_salary: e.target.value === "" ? null : Number(e.target.value) })} />
            </Field>
          </div>
        </Card>
        <Card title={`Match score weights (total ${weightTotal}%)`}>
          {Object.entries(r.score_weights).map(([k, v]) => (
            <Field key={k} label={WEIGHT_LABELS[k] ?? k}>
              <input className={`${inputClass} mb-2`} type="number" min={0} max={100} value={v}
                onChange={(e) => setR({ ...r, score_weights: { ...r.score_weights, [k]: Number(e.target.value) } })} />
            </Field>
          ))}
          {weightTotal !== 100 && <Alert kind="error">Weights must add up to 100.</Alert>}
        </Card>
        <Card title="Filters">
          <div className="space-y-3">
            <Field label="Allowed job titles">
              <TagInput label="Allowed job titles" value={r.allowed_titles} onChange={(v) => setR({ ...r, allowed_titles: v })} />
            </Field>
            <Field label="Allowed locations">
              <TagInput label="Allowed locations" value={r.allowed_locations} onChange={(v) => setR({ ...r, allowed_locations: v })} />
            </Field>
            <Field label="Company allowlist">
              <TagInput label="Company allowlist" value={r.company_allowlist} onChange={(v) => setR({ ...r, company_allowlist: v })} />
            </Field>
            <Field label="Company blocklist">
              <TagInput label="Company blocklist" value={r.company_blocklist} onChange={(v) => setR({ ...r, company_blocklist: v })} />
            </Field>
          </div>
        </Card>
        <Card title="Preferred resume per role">
          <PreferredResumes value={r.preferred_resume_by_role} onChange={(v) => setR({ ...r, preferred_resume_by_role: v })} />
        </Card>
        <Card title="Per-portal permissions">
          <p className="mb-3 text-xs text-muted">Auto-apply only takes effect for portals whose integration permits submission.</p>
          {["mock", "naukri", "linkedin", "indeed", "instahyre", "cutshort"].map((code) => {
            const p = r.portal_permissions[code] ?? { enabled: true, auto_apply: false };
            const set = (patch: Partial<typeof p>) =>
              setR({ ...r, portal_permissions: { ...r.portal_permissions, [code]: { ...p, ...patch } } });
            return (
              <div key={code} className="flex items-center justify-between border-b border-line py-2 text-sm last:border-0">
                <span className="capitalize">{code}</span>
                <span className="flex gap-4">
                  <label className="flex items-center gap-1">
                    <input type="checkbox" checked={p.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> Enabled
                  </label>
                  <label className="flex items-center gap-1">
                    <input type="checkbox" checked={p.auto_apply} onChange={(e) => set({ auto_apply: e.target.checked })} /> Auto-apply
                  </label>
                </span>
              </div>
            );
          })}
        </Card>
        <div className="lg:col-span-2">
          {msg && (
            <div className="mb-3">
              <Alert kind={msg.kind}>{msg.text}</Alert>
            </div>
          )}
          <Button type="submit" disabled={busy || weightTotal !== 100}>
            {busy ? "Saving…" : "Save rules"}
          </Button>
        </div>
      </form>
    </>
  );
}
