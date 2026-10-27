"use client";

import { useState, type FormEvent } from "react";
import { CompletenessMeter } from "@/components/CompletenessMeter";
import { TagInput } from "@/components/TagInput";
import { Alert, Button, Card, Field, inputClass, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { CandidateSkill, Certification, Education, Employment, EmploymentInput, Profile } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Msg = { kind: "success" | "error"; text: string } | undefined;

const numOrNull = (v: string) => (v.trim() === "" ? null : Number(v));
const strOrNull = (v: string) => (v.trim() === "" ? null : v.trim());

export default function ProfilePage() {
  const { data, error, loading, sleeping, setData, reload } = useApi<Profile>("/profile");

  if (loading && !data) return <Loading sleeping={sleeping} />;
  if (error || !data) return <Alert kind="error">{error?.message ?? "Failed to load"}</Alert>;

  return (
    <>
      <PageHeader
        title="My Profile"
        description="Your master profile. Only enter facts you can stand behind: nothing here is invented or auto-filled."
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <BasicsForm profile={data} onSaved={setData} />
          <EmploymentSection profile={data} onChanged={reload} />
          <SkillsSection profile={data} onSaved={setData} />
          <EducationSection profile={data} onSaved={setData} />
        </div>
        <div className="space-y-4">
          <Card>
            <CompletenessMeter completeness={data.completeness} />
          </Card>
          <Alert>
            Resume upload and automatic field extraction arrive with the Resume Library (Phase 3). Until then, enter
            details here.
          </Alert>
        </div>
      </div>
    </>
  );
}

function useSaver() {
  const [msg, setMsg] = useState<Msg>();
  const [busy, setBusy] = useState(false);
  async function run<T>(fn: () => Promise<T>, ok = "Saved"): Promise<T | undefined> {
    setBusy(true);
    setMsg(undefined);
    try {
      const r = await fn();
      setMsg({ kind: "success", text: ok });
      return r;
    } catch (e) {
      setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Save failed" });
    } finally {
      setBusy(false);
    }
  }
  return { msg, busy, run };
}

function BasicsForm({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const [f, setF] = useState({
    full_name: profile.full_name,
    email: profile.email ?? "",
    phone: profile.phone ?? "",
    location: profile.location ?? "",
    headline: profile.headline ?? "",
    summary: profile.summary ?? "",
    total_experience_years: profile.total_experience_years?.toString() ?? "",
    preferred_roles: profile.preferred_roles,
    preferred_locations: profile.preferred_locations,
    work_arrangement: profile.work_arrangement,
    salary_currency: profile.salary_currency,
    salary_min: profile.salary_min?.toString() ?? "",
    salary_max: profile.salary_max?.toString() ?? "",
    notice_period_days: profile.notice_period_days?.toString() ?? "",
    target_experience_min: profile.target_experience_min?.toString() ?? "",
    target_experience_max: profile.target_experience_max?.toString() ?? "",
    excluded_companies: profile.excluded_companies,
  });
  const { msg, busy, run } = useSaver();
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.value });

  async function save(e: FormEvent) {
    e.preventDefault();
    const body = {
      full_name: f.full_name.trim(),
      email: strOrNull(f.email),
      phone: strOrNull(f.phone),
      location: strOrNull(f.location),
      headline: strOrNull(f.headline),
      summary: strOrNull(f.summary),
      total_experience_years: numOrNull(f.total_experience_years),
      preferred_roles: f.preferred_roles,
      preferred_locations: f.preferred_locations,
      work_arrangement: f.work_arrangement,
      salary_currency: f.salary_currency.toUpperCase(),
      salary_min: numOrNull(f.salary_min),
      salary_max: numOrNull(f.salary_max),
      notice_period_days: numOrNull(f.notice_period_days),
      target_experience_min: numOrNull(f.target_experience_min),
      target_experience_max: numOrNull(f.target_experience_max),
      excluded_companies: f.excluded_companies,
    };
    const p = await run(() => api<Profile>("/profile", { method: "PATCH", body }));
    if (p) onSaved(p);
  }

  return (
    <Card title="Contact, summary and job preferences">
      <form onSubmit={save} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name">
            <input className={inputClass} value={f.full_name} onChange={set("full_name")} />
          </Field>
          <Field label="Contact email">
            <input className={inputClass} type="email" value={f.email} onChange={set("email")} />
          </Field>
          <Field label="Phone">
            <input className={inputClass} value={f.phone} onChange={set("phone")} />
          </Field>
          <Field label="Current location">
            <input className={inputClass} value={f.location} onChange={set("location")} />
          </Field>
          <Field label="Professional headline">
            <input className={inputClass} value={f.headline} onChange={set("headline")} />
          </Field>
          <Field label="Total experience (years)">
            <input className={inputClass} type="number" step="0.5" min="0" value={f.total_experience_years} onChange={set("total_experience_years")} />
          </Field>
        </div>
        <Field label="Professional summary">
          <textarea className={`${inputClass} min-h-28`} value={f.summary} onChange={set("summary")} />
        </Field>
        <hr className="border-line" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Preferred roles">
            <TagInput label="Preferred roles" value={f.preferred_roles} onChange={(v) => setF({ ...f, preferred_roles: v })} placeholder="e.g. QA Lead" />
          </Field>
          <Field label="Preferred locations">
            <TagInput label="Preferred locations" value={f.preferred_locations} onChange={(v) => setF({ ...f, preferred_locations: v })} placeholder="e.g. Bengaluru, Remote" />
          </Field>
          <Field label="Work arrangement">
            <select className={inputClass} value={f.work_arrangement} onChange={set("work_arrangement")}>
              <option value="any">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </Field>
          <Field label="Notice period (days)">
            <input className={inputClass} type="number" min="0" value={f.notice_period_days} onChange={set("notice_period_days")} />
          </Field>
          <Field label="Expected salary (min / max per year)">
            <div className="flex gap-2">
              <input aria-label="Salary currency" className={`${inputClass} w-20`} maxLength={3} value={f.salary_currency} onChange={set("salary_currency")} />
              <input aria-label="Salary minimum" className={inputClass} type="number" min="0" value={f.salary_min} onChange={set("salary_min")} />
              <input aria-label="Salary maximum" className={inputClass} type="number" min="0" value={f.salary_max} onChange={set("salary_max")} />
            </div>
          </Field>
          <Field label="Target roles' experience requirement (years min / max)">
            <div className="flex gap-2">
              <input aria-label="Experience minimum" className={inputClass} type="number" min="0" value={f.target_experience_min} onChange={set("target_experience_min")} />
              <input aria-label="Experience maximum" className={inputClass} type="number" min="0" value={f.target_experience_max} onChange={set("target_experience_max")} />
            </div>
          </Field>
        </div>
        <Field label="Excluded companies">
          <TagInput label="Excluded companies" value={f.excluded_companies} onChange={(v) => setF({ ...f, excluded_companies: v })} />
        </Field>
        {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save profile"}
        </Button>
      </form>
    </Card>
  );
}

const EMPTY_JOB: EmploymentInput = {
  company: "",
  title: "",
  location: null,
  start_date: "",
  end_date: null,
  is_current: false,
  description: null,
  achievements: [],
  sort_order: 0,
};

function EmploymentSection({ profile, onChanged }: { profile: Profile; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState<{ id: string | null; data: EmploymentInput } | null>(null);
  const { msg, busy, run } = useSaver();

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    const body = { ...editing.data, end_date: editing.data.is_current ? null : editing.data.end_date || null };
    const ok = await run(() =>
      editing.id
        ? api(`/profile/employment/${editing.id}`, { method: "PUT", body })
        : api("/profile/employment", { method: "POST", body }),
    );
    if (ok) {
      setEditing(null);
      await onChanged();
    }
  }

  async function remove(job: Employment) {
    if (!confirm(`Delete ${job.title} at ${job.company}?`)) return;
    await run(() => api(`/profile/employment/${job.id}`, { method: "DELETE" }), "Deleted");
    await onChanged();
  }

  const d = editing?.data;
  const upd = (patch: Partial<EmploymentInput>) => editing && setEditing({ ...editing, data: { ...editing.data, ...patch } });

  return (
    <Card title="Employment history">
      {profile.employment.length === 0 && <p className="mb-3 text-sm text-muted">No employment entries yet.</p>}
      <ul className="divide-y divide-line">
        {profile.employment.map((job) => (
          <li key={job.id} className="flex flex-wrap items-start justify-between gap-2 py-3 text-sm">
            <div>
              <p className="font-medium">
                {job.title} · {job.company}
              </p>
              <p className="text-muted">
                {job.start_date} – {job.is_current ? "Present" : job.end_date}
                {job.location ? ` · ${job.location}` : ""}
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setEditing({ id: job.id, data: { ...job } })}>
                Edit
              </Button>
              <Button variant="secondary" onClick={() => remove(job)}>
                Delete
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {d ? (
        <form onSubmit={save} className="mt-4 space-y-3 rounded-lg border border-line p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Job title">
              <input className={inputClass} required value={d.title} onChange={(e) => upd({ title: e.target.value })} />
            </Field>
            <Field label="Company">
              <input className={inputClass} required value={d.company} onChange={(e) => upd({ company: e.target.value })} />
            </Field>
            <Field label="Start date">
              <input className={inputClass} type="date" required value={d.start_date} onChange={(e) => upd({ start_date: e.target.value })} />
            </Field>
            <Field label="End date">
              <input className={inputClass} type="date" disabled={d.is_current} value={d.end_date ?? ""} onChange={(e) => upd({ end_date: e.target.value })} />
            </Field>
            <Field label="Location">
              <input className={inputClass} value={d.location ?? ""} onChange={(e) => upd({ location: strOrNull(e.target.value) })} />
            </Field>
            <label className="flex items-center gap-2 pt-6 text-sm">
              <input type="checkbox" checked={d.is_current} onChange={(e) => upd({ is_current: e.target.checked })} />I
              currently work here
            </label>
          </div>
          <Field label="Description">
            <textarea className={`${inputClass} min-h-20`} value={d.description ?? ""} onChange={(e) => upd({ description: strOrNull(e.target.value) })} />
          </Field>
          <Field label="Achievements (one per line)">
            <textarea
              className={`${inputClass} min-h-20`}
              value={d.achievements.join("\n")}
              onChange={(e) => upd({ achievements: e.target.value.split("\n").filter((l) => l.trim()) })}
            />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {editing?.id ? "Update entry" : "Add entry"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <Button variant="secondary" className="mt-3" onClick={() => setEditing({ id: null, data: { ...EMPTY_JOB } })}>
          Add employment
        </Button>
      )}
      {msg && (
        <div className="mt-3">
          <Alert kind={msg.kind}>{msg.text}</Alert>
        </div>
      )}
    </Card>
  );
}

type SkillRow = Omit<CandidateSkill, "id">;

function SkillsSection({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const [rows, setRows] = useState<SkillRow[]>(profile.skills.map(({ id: _id, ...s }) => s));
  const [draft, setDraft] = useState("");
  const { msg, busy, run } = useSaver();

  function add() {
    const name = draft.trim();
    if (name && !rows.some((r) => r.name.toLowerCase() === name.toLowerCase())) {
      setRows([...rows, { name, level: null, years_experience: null, is_primary: false }]);
    }
    setDraft("");
  }
  const upd = (i: number, patch: Partial<SkillRow>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function save() {
    const p = await run(() => api<Profile>("/profile/skills", { method: "PUT", body: rows }));
    if (p) onSaved(p);
  }

  return (
    <Card title="Skills">
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={r.name} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="min-w-40 flex-1 font-medium">{r.name}</span>
            <select
              aria-label={`${r.name} level`}
              className={`${inputClass} w-36`}
              value={r.level ?? ""}
              onChange={(e) => upd(i, { level: (e.target.value || null) as SkillRow["level"] })}
            >
              <option value="">Level…</option>
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
              <option value="expert">Expert</option>
            </select>
            <input
              aria-label={`${r.name} years`}
              className={`${inputClass} w-24`}
              type="number"
              min="0"
              step="0.5"
              placeholder="Years"
              value={r.years_experience ?? ""}
              onChange={(e) => upd(i, { years_experience: numOrNull(e.target.value) })}
            />
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={r.is_primary} onChange={(e) => upd(i, { is_primary: e.target.checked })} />
              Primary
            </label>
            <button type="button" className="text-muted hover:text-red-600" aria-label={`Remove ${r.name}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              ×
            </button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          aria-label="New skill"
          className={inputClass}
          placeholder="Add a skill, e.g. Playwright"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" variant="secondary" onClick={add}>
          Add
        </Button>
      </div>
      {msg && (
        <div className="mt-3">
          <Alert kind={msg.kind}>{msg.text}</Alert>
        </div>
      )}
      <Button className="mt-3" onClick={save} disabled={busy}>
        Save skills
      </Button>
    </Card>
  );
}

function EducationSection({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const [education, setEducation] = useState<Education[]>(profile.education);
  const [certs, setCerts] = useState<Certification[]>(profile.certifications);
  const { msg, busy, run } = useSaver();

  async function save() {
    const body = {
      education: education.filter((e) => e.institution.trim() && e.degree.trim()),
      certifications: certs.filter((c) => c.name.trim()),
    };
    const p = await run(() => api<Profile>("/profile", { method: "PATCH", body }));
    if (p) onSaved(p);
  }

  return (
    <Card title="Education and certifications">
      <p className="mb-2 text-sm font-medium">Education</p>
      {education.map((e, i) => (
        <div key={i} className="mb-2 flex flex-wrap gap-2">
          <input aria-label="Institution" className={`${inputClass} flex-1`} placeholder="Institution" value={e.institution}
            onChange={(ev) => setEducation(education.map((x, j) => (j === i ? { ...x, institution: ev.target.value } : x)))} />
          <input aria-label="Degree" className={`${inputClass} flex-1`} placeholder="Degree" value={e.degree}
            onChange={(ev) => setEducation(education.map((x, j) => (j === i ? { ...x, degree: ev.target.value } : x)))} />
          <input aria-label="End year" className={`${inputClass} w-28`} type="number" placeholder="Year" value={e.end_year ?? ""}
            onChange={(ev) => setEducation(education.map((x, j) => (j === i ? { ...x, end_year: numOrNull(ev.target.value) } : x)))} />
          <Button type="button" variant="secondary" onClick={() => setEducation(education.filter((_, j) => j !== i))}>Remove</Button>
        </div>
      ))}
      <Button type="button" variant="secondary" onClick={() => setEducation([...education, { institution: "", degree: "" }])}>
        Add education
      </Button>
      <p className="mb-2 mt-5 text-sm font-medium">Certifications</p>
      {certs.map((c, i) => (
        <div key={i} className="mb-2 flex flex-wrap gap-2">
          <input aria-label="Certification" className={`${inputClass} flex-1`} placeholder="Certification" value={c.name}
            onChange={(ev) => setCerts(certs.map((x, j) => (j === i ? { ...x, name: ev.target.value } : x)))} />
          <input aria-label="Issuer" className={`${inputClass} flex-1`} placeholder="Issuer" value={c.issuer ?? ""}
            onChange={(ev) => setCerts(certs.map((x, j) => (j === i ? { ...x, issuer: strOrNull(ev.target.value) } : x)))} />
          <Button type="button" variant="secondary" onClick={() => setCerts(certs.filter((_, j) => j !== i))}>Remove</Button>
        </div>
      ))}
      <Button type="button" variant="secondary" onClick={() => setCerts([...certs, { name: "" }])}>
        Add certification
      </Button>
      {msg && (
        <div className="mt-3">
          <Alert kind={msg.kind}>{msg.text}</Alert>
        </div>
      )}
      <div>
        <Button className="mt-4" onClick={save} disabled={busy}>
          Save education and certifications
        </Button>
      </div>
    </Card>
  );
}
