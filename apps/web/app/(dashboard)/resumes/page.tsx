"use client";

import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, inputClass, Loading, PageHeader } from "@/components/ui";
import { api, ApiError, apiUpload } from "@/lib/api";
import type { ParsedEmployment, Profile, ResumeItem, ResumeSuggestions, UploadResult } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const KIND_LABEL: Record<ResumeItem["kind"], string> = {
  uploaded: "Uploaded",
  master: "Master (generated)",
  tailored: "Tailored (generated)",
};

function kb(n: number) {
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

export default function ResumesPage() {
  const list = useApi<ResumeItem[]>("/resumes");
  const [review, setReview] = useState<UploadResult>();
  const [msg, setMsg] = useState<{ kind: "success" | "error" | "info"; text: string }>();
  const [busy, setBusy] = useState(false);

  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem("file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg(undefined);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await apiUpload<UploadResult>("/resumes/upload", form);
      setReview(r);
      setMsg(r.duplicate ? { kind: "info", text: "This exact file is already in your library." } : undefined);
      input.value = "";
      await list.reload();
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof ApiError ? err.message : "Upload failed" });
    } finally {
      setBusy(false);
    }
  }

  async function generateMaster() {
    setBusy(true);
    setMsg(undefined);
    try {
      const r = await api<{ resume: ResumeItem; created: boolean }>("/resumes/generate", { method: "POST", body: {} });
      setMsg({
        kind: "success",
        text: r.created ? `Master resume v${r.resume.version} generated.` : "No profile changes since the last version.",
      });
      await list.reload();
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof ApiError ? err.message : "Generation failed" });
    } finally {
      setBusy(false);
    }
  }

  async function remove(r: ResumeItem) {
    if (!confirm(`Delete ${r.label} v${r.version}?`)) return;
    await api(`/resumes/${r.id}`, { method: "DELETE" });
    await list.reload();
  }

  return (
    <>
      <PageHeader
        title="Resume Library"
        description="Upload your resume to pre-fill your profile, and generate master or job-tailored versions from your verified profile."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Upload a resume">
          <form onSubmit={upload} className="space-y-3">
            <input
              name="file"
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              aria-label="Resume file"
              className="block w-full text-sm"
              required
            />
            <p className="text-xs text-muted">PDF or Word (.docx), up to 2 MB. Stored privately in your database.</p>
            <Button type="submit" disabled={busy}>
              {busy ? "Working…" : "Upload and read"}
            </Button>
          </form>
        </Card>
        <Card title="Generate from your profile">
          <p className="mb-3 text-sm text-muted">
            Built only from your profile: nothing is invented. Each change creates a new version; identical content is not
            duplicated. Tailored versions are made from a job&apos;s page.
          </p>
          <Button onClick={generateMaster} disabled={busy}>
            Generate master resume
          </Button>
        </Card>
      </div>
      {msg && (
        <div className="mt-4">
          <Alert kind={msg.kind}>{msg.text}</Alert>
        </div>
      )}
      {review && <ReviewPanel result={review} onDone={() => setReview(undefined)} />}

      <Card title="Versions" className="mt-4">
        {list.loading && !list.data ? (
          <Loading sleeping={list.sleeping} />
        ) : !list.data?.length ? (
          <p className="text-sm text-muted">No resumes yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-2">Resume</th>
                  <th>Type</th>
                  <th>Version</th>
                  <th>Created</th>
                  <th>SHA-256</th>
                  <th>Download</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {list.data.map((r) => (
                  <tr key={r.id}>
                    <td className="py-2 pr-2">
                      {r.label}
                      <span className="block text-xs text-muted">{r.file_name}</span>
                    </td>
                    <td className="pr-2">{KIND_LABEL[r.kind]}</td>
                    <td className="pr-2">v{r.version}</td>
                    <td className="pr-2 text-xs">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="pr-2 font-mono text-xs" title={r.sha256}>
                      {r.sha256.slice(0, 10)}…
                    </td>
                    <td className="space-x-2 whitespace-nowrap pr-2">
                      {r.kind === "uploaded" ? (
                        <a className="text-brand hover:underline" href={`/api/resumes/${r.id}/download?format=${r.mime_type === "application/pdf" ? "pdf" : "docx"}`}>
                          Original ({kb(r.size_bytes)})
                        </a>
                      ) : (
                        <>
                          <a className="text-brand hover:underline" href={`/api/resumes/${r.id}/download?format=docx`}>DOCX</a>
                          <a className="text-brand hover:underline" href={`/api/resumes/${r.id}/download?format=pdf`}>PDF</a>
                        </>
                      )}
                    </td>
                    <td>
                      <button className="text-xs text-muted hover:text-red-600" onClick={() => remove(r)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

type ScalarKey = "full_name" | "headline" | "email" | "phone" | "summary" | "total_experience_years";
const SCALARS: [ScalarKey, string][] = [
  ["full_name", "Full name"],
  ["headline", "Headline"],
  ["email", "Email"],
  ["phone", "Phone"],
  ["total_experience_years", "Total experience (years)"],
  ["summary", "Summary"],
];

function ReviewPanel({ result, onDone }: { result: UploadResult; onDone: () => void }) {
  const s: ResumeSuggestions = result.suggestions;
  const profile = useApi<Profile>("/profile");
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [skills, setSkills] = useState<Record<string, boolean>>({});
  const [certs, setCerts] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string }>();

  if (profile.loading || !profile.data) return <Loading sleeping={profile.sleeping} />;
  const p = profile.data;
  const have = new Set(p.skills.map((x) => x.name.toLowerCase()));
  const newSkills = s.skills.filter((x) => !have.has(x.toLowerCase()));

  async function apply() {
    const body: Record<string, unknown> = {};
    for (const [k] of SCALARS) if (picked[k] && s[k] != null) body[k] = s[k];
    if (picked.links && Object.keys(s.links).length) body.links = { ...p.links, ...s.links };
    const chosenCerts = s.certifications.filter((c) => certs[c]).map((name) => ({ name }));
    if (chosenCerts.length) body.certifications = [...p.certifications, ...chosenCerts];
    try {
      await api(`/resumes/${result.resume.id}/apply`, {
        method: "POST",
        body: { profile: body, add_skills: newSkills.filter((x) => skills[x]) },
      });
      setMsg({ kind: "success", text: "Selected values copied to your profile." });
      await profile.reload();
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof ApiError ? err.message : "Could not apply" });
    }
  }

  const row = (label: string, current: unknown, found: unknown, key: string) => (
    <tr key={key}>
      <td className="py-2 pr-2 align-top">
        <input type="checkbox" aria-label={`Use ${label}`} disabled={found == null || found === ""} checked={!!picked[key]}
          onChange={(e) => setPicked({ ...picked, [key]: e.target.checked })} />
      </td>
      <td className="pr-2 align-top font-medium">{label}</td>
      <td className="pr-2 align-top text-muted">{current == null || current === "" ? "—" : String(current)}</td>
      <td className="align-top whitespace-pre-wrap">{found == null || found === "" ? <span className="text-muted">not found</span> : String(found)}</td>
    </tr>
  );

  return (
    <Card title="Review what was read from your resume" className="mt-4">
      <Alert>
        Nothing has been changed yet. Tick only values that are correct. Unticked values are ignored. Reading is rule-based
        and can miss or misread things.
      </Alert>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs text-muted">
            <tr><th className="w-8" /><th>Field</th><th>Your profile now</th><th>Found in resume</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {SCALARS.map(([k, label]) => row(label, p[k], s[k], k))}
            {row("Links", Object.values(p.links).join(", "), Object.values(s.links).join(", ") || null, "links")}
          </tbody>
        </table>
      </div>
      {newSkills.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-sm font-medium">Skills found that are not in your profile</p>
          <div className="flex flex-wrap gap-3 text-sm">
            {newSkills.map((x) => (
              <label key={x} className="flex items-center gap-1">
                <input type="checkbox" checked={!!skills[x]} onChange={(e) => setSkills({ ...skills, [x]: e.target.checked })} />
                {x}
              </label>
            ))}
          </div>
        </div>
      )}
      {s.certifications.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-sm font-medium">Certifications</p>
          {s.certifications.map((c) => (
            <label key={c} className="flex items-center gap-1 text-sm">
              <input type="checkbox" checked={!!certs[c]} onChange={(e) => setCerts({ ...certs, [c]: e.target.checked })} />
              {c}
            </label>
          ))}
        </div>
      )}
      <div className="mt-4 flex gap-2">
        <Button onClick={apply}>Copy ticked values to profile</Button>
        <Button variant="secondary" onClick={onDone}>Close</Button>
      </div>
      {msg && <div className="mt-3"><Alert kind={msg.kind}>{msg.text}</Alert></div>}
      {s.employment.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-sm font-medium">Employment entries found ({s.employment.length})</p>
          <p className="mb-2 text-xs text-muted">Check the title and company split, then add each one you want.</p>
          <div className="space-y-2">
            {s.employment.map((e, i) => <EmploymentSuggestion key={i} e={e} />)}
          </div>
        </div>
      )}
      {s.education_text && (
        <div className="mt-5">
          <p className="text-sm font-medium">Education section (add it in My Profile)</p>
          <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-subtle p-3 text-xs">{s.education_text}</pre>
        </div>
      )}
    </Card>
  );
}

function EmploymentSuggestion({ e }: { e: ParsedEmployment }) {
  const [first, ...rest] = e.heading.split(",");
  const [title, setTitle] = useState(first?.trim() ?? "");
  const [company, setCompany] = useState(rest.join(",").trim());
  const [start, setStart] = useState(e.start_date ?? "");
  const [end, setEnd] = useState(e.end_date ?? "");
  const [state, setState] = useState<string>();

  async function add() {
    try {
      await api("/profile/employment", {
        method: "POST",
        body: { title, company, start_date: start, end_date: e.is_current ? null : end || null, is_current: e.is_current, achievements: [] },
      });
      setState("Added");
    } catch (err) {
      setState(err instanceof ApiError ? err.message : "Failed");
    }
  }

  return (
    <div className="grid gap-2 rounded-lg border border-line p-3 text-sm md:grid-cols-5">
      <Field label="Title"><input className={inputClass} value={title} onChange={(x) => setTitle(x.target.value)} /></Field>
      <Field label="Company"><input className={inputClass} value={company} onChange={(x) => setCompany(x.target.value)} /></Field>
      <Field label="Start"><input className={inputClass} type="date" value={start} onChange={(x) => setStart(x.target.value)} /></Field>
      <Field label="End" hint={e.is_current ? "Current role" : undefined}>
        <input className={inputClass} type="date" disabled={e.is_current} value={end} onChange={(x) => setEnd(x.target.value)} />
      </Field>
      <div className="flex items-end gap-2">
        <Button variant="secondary" onClick={add} disabled={state === "Added" || !title || !company || !start}>Add</Button>
        {state && <span className="text-xs text-muted">{state}</span>}
      </div>
    </div>
  );
}
