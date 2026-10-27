"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { TagInput } from "./TagInput";
import { Alert, Button, Card, Field, inputClass } from "./ui";

const PORTALS = [
  ["linkedin", "LinkedIn"],
  ["indeed", "Indeed"],
  ["naukri", "Naukri"],
  ["instahyre", "Instahyre"],
  ["cutshort", "Cutshort"],
] as const;

const EMPTY = {
  portal: "linkedin",
  url: "",
  title: "",
  company: "",
  location: "",
  work_arrangement: "",
  description: "",
  experience_min: "",
  experience_max: "",
  salary_min: "",
  salary_max: "",
};

const num = (v: string) => (v.trim() === "" ? null : Number(v));

/** Add a real listing you found on a portal. The app stores what you paste; it never opens the link. */
export function AddJobForm() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(EMPTY);
  const [skills, setSkills] = useState<string[]>([]);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const r = await api<{ job_id: string; outcome: string }>("/jobs/manual", {
        method: "POST",
        body: {
          portal: f.portal,
          url: f.url.trim(),
          title: f.title,
          company: f.company,
          location: f.location || null,
          work_arrangement: f.work_arrangement || null,
          description: f.description || null,
          skills,
          experience_min: num(f.experience_min),
          experience_max: num(f.experience_max),
          salary_min: num(f.salary_min),
          salary_max: num(f.salary_max),
          salary_currency: f.salary_min || f.salary_max ? "INR" : null,
        },
      });
      router.push(`/jobs/${r.job_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the job");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm">
            Found a real job on LinkedIn, Indeed, Naukri, Instahyre or Cutshort? Add it here to score it and prepare documents.
          </p>
          <Button variant="secondary" onClick={() => setOpen(true)}>Add a job you found</Button>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Add a job you found">
      <p className="mb-3 text-xs text-muted">
        Paste the details from the listing. The app stores only what you enter and never visits the link (the portals do not
        permit automated access).
      </p>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
        <Field label="Portal">
          <select className={inputClass} value={f.portal} onChange={set("portal")}>
            {PORTALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Listing link (https://…)">
          <input className={inputClass} required pattern="https://.+" value={f.url} onChange={set("url")} />
        </Field>
        <Field label="Job title">
          <input className={inputClass} required minLength={2} value={f.title} onChange={set("title")} />
        </Field>
        <Field label="Company">
          <input className={inputClass} required value={f.company} onChange={set("company")} />
        </Field>
        <Field label="Location">
          <input className={inputClass} value={f.location} onChange={set("location")} />
        </Field>
        <Field label="Arrangement">
          <select className={inputClass} value={f.work_arrangement} onChange={set("work_arrangement")}>
            <option value="">Not stated</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
          </select>
        </Field>
        <Field label="Experience required (years min / max)">
          <div className="flex gap-2">
            <input aria-label="Experience min" className={inputClass} type="number" min={0} value={f.experience_min} onChange={set("experience_min")} />
            <input aria-label="Experience max" className={inputClass} type="number" min={0} value={f.experience_max} onChange={set("experience_max")} />
          </div>
        </Field>
        <Field label="Salary per year, INR (min / max, if shown)">
          <div className="flex gap-2">
            <input aria-label="Salary min" className={inputClass} type="number" min={0} value={f.salary_min} onChange={set("salary_min")} />
            <input aria-label="Salary max" className={inputClass} type="number" min={0} value={f.salary_max} onChange={set("salary_max")} />
          </div>
        </Field>
        <div className="md:col-span-2">
          <Field label="Description">
            <textarea className={`${inputClass} min-h-32`} maxLength={20000} value={f.description} onChange={set("description")} />
          </Field>
        </div>
        <div className="md:col-span-2">
          <Field label="Skills listed">
            <TagInput label="Skills listed" value={skills} onChange={setSkills} />
          </Field>
        </div>
        {error && <div className="md:col-span-2"><Alert kind="error">{error}</Alert></div>}
        <div className="flex gap-2 md:col-span-2">
          <Button type="submit" disabled={busy}>{busy ? "Adding…" : "Add and score"}</Button>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}
