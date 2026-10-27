import type { Completeness } from "@/lib/types";

export function CompletenessMeter({ completeness }: { completeness: Completeness }) {
  const { score, missing } = completeness;
  const color = score >= 80 ? "bg-emerald-500" : score >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span className="font-medium">Profile completeness</span>
        <span data-testid="completeness-score">{score}%</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-subtle"
        role="progressbar"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Profile completeness"
      >
        <div className={`h-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      {missing.length > 0 ? (
        <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-muted">
          {missing.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-muted">All profile checks pass.</p>
      )}
    </div>
  );
}
