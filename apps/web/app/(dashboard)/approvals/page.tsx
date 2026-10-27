"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Button, Card, inputClass, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { ApprovalItem, DocumentItem, ScreeningAnswer } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const STATUS_STYLE: Record<ApprovalItem["status"], string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  rejected: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
  expired: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
};

export default function ApprovalsPage() {
  const [tab, setTab] = useState<"pending" | "decided">("pending");
  const list = useApi<ApprovalItem[]>("/approvals");
  const items = (list.data ?? []).filter((a) => (tab === "pending" ? a.status === "pending" : a.status !== "pending"));

  return (
    <>
      <PageHeader
        title="Approval Queue"
        description="Applications the rules engine prepared but will not submit without you: auto-apply is off, a portal requires manual submission, eligibility or salary is unknown, or a screening answer needs confirmation."
      />
      <div className="mb-4 flex gap-2" role="tablist">
        {(["pending", "decided"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm ${tab === t ? "bg-brand/10 font-medium text-brand" : "hover:bg-subtle"}`}
          >
            {t === "pending" ? `Pending (${(list.data ?? []).filter((a) => a.status === "pending").length})` : "Decided"}
          </button>
        ))}
      </div>
      {list.loading && !list.data ? (
        <Loading sleeping={list.sleeping} />
      ) : list.error ? (
        <Alert kind="error">{list.error.message}</Alert>
      ) : items.length === 0 ? (
        <Alert>{tab === "pending" ? "Nothing waiting for you." : "No decisions yet."}</Alert>
      ) : (
        <div className="space-y-3">
          {items.map((a) => <ApprovalCard key={a.id} item={a} onDone={list.reload} />)}
        </div>
      )}
    </>
  );
}

function ApprovalCard({ item, onDone }: { item: ApprovalItem; onDone: () => Promise<void> }) {
  const p = item.payload;
  const [reviewed, setReviewed] = useState(false);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string }>();
  const [answers, setAnswers] = useState<ScreeningAnswer[]>();

  async function decide(kind: "approve" | "reject") {
    setMsg(undefined);
    try {
      const body = kind === "approve" ? { confirm_reviewed: reviewed, note: note || null } : { note: note || null };
      const r = await api<{ outcome: string }>(`/approvals/${item.id}/${kind}`, { method: "POST", body });
      setMsg({ kind: "success", text: r.outcome });
      await onDone();
    } catch (e) {
      setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Failed" });
    }
  }

  async function loadAnswers() {
    if (!p.screening_answers_id) return;
    const d = await api<DocumentItem>(`/documents/${p.screening_answers_id}`);
    setAnswers(d.content.answers as ScreeningAnswer[]);
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">
            <Link href={`/jobs/${p.job_id}`} className="hover:underline">{p.title}</Link>
          </h3>
          <p className="text-sm text-muted">
            {p.company} · {p.portal ?? "unknown portal"} · score {p.score ?? "n/a"} · requested {new Date(item.created_at).toLocaleString()}
          </p>
        </div>
        <span data-testid="approval-status" className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[item.status]}`}>
          {item.status}
        </span>
      </div>

      <p className="mt-3 text-sm font-medium">Why it needs you</p>
      <ul className="list-disc pl-5 text-sm">
        {p.reasons.map((r) => <li key={r}>{r}</li>)}
      </ul>

      <p className="mt-3 text-sm font-medium">Prepared documents</p>
      <p className="flex flex-wrap gap-x-3 text-sm">
        {p.resume_id && (
          <span>
            Resume: <a className="text-brand hover:underline" href={`/api/resumes/${p.resume_id}/download?format=pdf`}>PDF</a> ·{" "}
            <a className="text-brand hover:underline" href={`/api/resumes/${p.resume_id}/download?format=docx`}>DOCX</a>
          </span>
        )}
        {p.cover_letter_id && (
          <span>
            Cover letter: <a className="text-brand hover:underline" href={`/api/documents/${p.cover_letter_id}/download?format=pdf`}>PDF</a>
          </span>
        )}
        {p.screening_answers_id && (
          <button className="text-brand hover:underline" onClick={loadAnswers}>Show screening answers</button>
        )}
      </p>
      {answers && (
        <ul className="mt-2 space-y-1 text-sm">
          {answers.map((a) => (
            <li key={a.question} className="rounded-lg border border-line p-2">
              <p className="font-medium">{a.question}</p>
              <p className={a.answer ? "" : "text-muted"}>{a.answer ?? "No draft — answer this yourself"}</p>
              {a.needs_confirmation && <p className="text-xs text-amber-700 dark:text-amber-300">Review: {a.reason}</p>}
            </li>
          ))}
        </ul>
      )}

      {item.status === "pending" ? (
        <div className="mt-4 space-y-2">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
            I reviewed the job, the documents and every flagged answer.
          </label>
          <input aria-label="Decision note" className={inputClass} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <Button disabled={!reviewed} onClick={() => decide("approve")}>Approve</Button>
            <Button variant="secondary" onClick={() => decide("reject")}>Reject</Button>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted">
          {item.status} {item.decided_at ? new Date(item.decided_at).toLocaleString() : ""}
          {p.outcome ? ` — ${p.outcome}` : ""}
          {p.decision_note ? ` (note: ${p.decision_note})` : ""}
        </p>
      )}
      {msg && <div className="mt-2"><Alert kind={msg.kind}>{msg.text}</Alert></div>}
    </Card>
  );
}
