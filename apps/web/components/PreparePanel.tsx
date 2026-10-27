"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ApplicationItem, CoverLetterContent, DocumentItem, ResumeItem, ScreeningAnswer } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Alert, Button, Card, inputClass } from "./ui";

type Msg = { kind: "success" | "error" | "info"; text: string } | undefined;

function errText(e: unknown) {
  if (e instanceof ApiError) return e.message;
  return "Something went wrong";
}

export function PreparePanel({ jobId, isSynthetic }: { jobId: string; isSynthetic: boolean }) {
  const resumes = useApi<ResumeItem[]>("/resumes");
  const letters = useApi<DocumentItem[]>(`/documents?job_id=${jobId}&kind=cover_letter`);
  const apps = useApi<ApplicationItem[]>(`/applications?job_id=${jobId}`);
  const [msg, setMsg] = useState<Msg>();
  const [edit, setEdit] = useState<CoverLetterContent>();
  const [questions, setQuestions] = useState("");
  const [answers, setAnswers] = useState<DocumentItem>();

  const tailored = resumes.data?.filter((r) => r.job_id === jobId).sort((a, b) => b.version - a.version)[0];
  const letter = letters.data?.[0];
  const app = apps.data?.[0];

  async function run(fn: () => Promise<void>) {
    setMsg(undefined);
    try {
      await fn();
    } catch (e) {
      setMsg({ kind: "error", text: errText(e) });
    }
  }

  const tailor = () =>
    run(async () => {
      const r = await api<{ resume: ResumeItem; created: boolean }>("/resumes/generate", { method: "POST", body: { job_id: jobId } });
      setMsg({ kind: "success", text: r.created ? `Tailored resume v${r.resume.version} created.` : "Already up to date." });
      await resumes.reload();
    });

  const writeLetter = () =>
    run(async () => {
      const r = await api<{ document: DocumentItem; created: boolean }>("/documents/cover-letter", { method: "POST", body: { job_id: jobId } });
      setMsg({ kind: "success", text: r.created ? `Cover letter v${r.document.version} created.` : "Already up to date." });
      await letters.reload();
    });

  const saveEdit = () =>
    run(async () => {
      if (!letter || !edit) return;
      await api(`/documents/${letter.id}`, { method: "PUT", body: edit });
      setEdit(undefined);
      setMsg({ kind: "success", text: "Saved as a new version." });
      await letters.reload();
    });

  const draftAnswers = () =>
    run(async () => {
      const qs = questions.split("\n").map((q) => q.trim()).filter(Boolean);
      if (!qs.length) return;
      const r = await api<{ document: DocumentItem }>("/documents/screening-answers", {
        method: "POST",
        body: { job_id: jobId, questions: qs },
      });
      setAnswers(r.document);
    });

  const track = () =>
    run(async () => {
      await api("/applications", {
        method: "POST",
        body: { job_id: jobId, resume_id: tailored?.id ?? null, cover_letter_id: letter?.id ?? null },
      });
      await apps.reload();
      setMsg({ kind: "success", text: "Added to your Application Tracker as a draft." });
    });

  return (
    <Card title="Prepare application">
      <div className="space-y-4 text-sm">
        <section>
          <p className="font-medium">1. Tailored resume</p>
          {tailored ? (
            <p className="text-muted">
              v{tailored.version} ·{" "}
              <a className="text-brand hover:underline" href={`/api/resumes/${tailored.id}/download?format=docx`}>DOCX</a>{" "}
              · <a className="text-brand hover:underline" href={`/api/resumes/${tailored.id}/download?format=pdf`}>PDF</a>
            </p>
          ) : (
            <p className="text-muted">None yet.</p>
          )}
          <Button variant="secondary" className="mt-1" onClick={tailor}>
            {tailored ? "Regenerate" : "Generate tailored resume"}
          </Button>
        </section>

        <section>
          <p className="font-medium">2. Cover letter</p>
          {letter && !edit && (
            <>
              <p className="text-muted">
                v{letter.version} ·{" "}
                <a className="text-brand hover:underline" href={`/api/documents/${letter.id}/download?format=docx`}>DOCX</a>{" "}
                · <a className="text-brand hover:underline" href={`/api/documents/${letter.id}/download?format=pdf`}>PDF</a>
              </p>
              <Button variant="secondary" className="mt-1 mr-2" onClick={() => setEdit(letter.content as unknown as CoverLetterContent)}>
                Edit
              </Button>
            </>
          )}
          {edit && (
            <div className="mt-2 space-y-2">
              <input aria-label="Greeting" className={inputClass} value={edit.greeting} onChange={(e) => setEdit({ ...edit, greeting: e.target.value })} />
              <textarea
                aria-label="Cover letter body"
                className={`${inputClass} min-h-48`}
                value={edit.paragraphs.join("\n\n")}
                onChange={(e) => setEdit({ ...edit, paragraphs: e.target.value.split(/\n\s*\n/) })}
              />
              <input aria-label="Sign-off" className={inputClass} value={edit.sign_off} onChange={(e) => setEdit({ ...edit, sign_off: e.target.value })} />
              <div className="flex gap-2">
                <Button onClick={saveEdit}>Save as new version</Button>
                <Button variant="secondary" onClick={() => setEdit(undefined)}>Cancel</Button>
              </div>
            </div>
          )}
          {!edit && (
            <Button variant="secondary" className="mt-1" onClick={writeLetter}>
              {letter ? "Regenerate" : "Write cover letter"}
            </Button>
          )}
        </section>

        <section>
          <p className="font-medium">3. Screening questions (optional)</p>
          <textarea
            aria-label="Screening questions"
            className={`${inputClass} mt-1 min-h-20`}
            placeholder="Paste the portal's questions, one per line"
            value={questions}
            onChange={(e) => setQuestions(e.target.value)}
          />
          <Button variant="secondary" className="mt-1" onClick={draftAnswers}>Draft answers</Button>
          {answers && (
            <ul className="mt-2 space-y-2">
              {(answers.content.answers as ScreeningAnswer[]).map((a) => (
                <li key={a.question} className="rounded-lg border border-line p-2">
                  <p className="font-medium">{a.question}</p>
                  <p className={a.answer ? "" : "text-muted"}>{a.answer ?? "No draft"}</p>
                  {a.needs_confirmation && (
                    <p className="text-xs text-amber-700 dark:text-amber-300">Review: {a.reason}</p>
                  )}
                </li>
              ))}
              <li>
                <a className="text-brand hover:underline" href={`/api/documents/${answers.id}/download?format=docx`}>Download answers (DOCX)</a>
              </li>
            </ul>
          )}
        </section>

        <section>
          <p className="font-medium">4. Track it</p>
          {app ? (
            <p>
              Status: <strong>{app.status}</strong>
              {app.is_simulated && " (simulated)"} ·{" "}
              <Link className="text-brand hover:underline" href={`/applications?focus=${app.id}`}>Open in tracker</Link>
            </p>
          ) : (
            <>
              <p className="text-muted">
                Apply on the portal yourself, then mark it submitted in the tracker.
                {isSynthetic && " For synthetic jobs the tracker can run a simulated submission."}
              </p>
              <Button className="mt-1" onClick={track}>Add to tracker</Button>
            </>
          )}
        </section>
        {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      </div>
    </Card>
  );
}
