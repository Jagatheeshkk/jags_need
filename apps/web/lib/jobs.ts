// Job Discovery filter state and its query-string encoding.

export interface Filters {
  q: string;
  role: string;
  location: string;
  work_arrangement: string;
  min_score: string;
  min_salary: string;
  eligible_only: boolean;
  include_expired: boolean;
  sort: "score" | "newest";
}

export const DEFAULT_FILTERS: Filters = {
  q: "",
  role: "",
  location: "",
  work_arrangement: "",
  min_score: "",
  min_salary: "",
  eligible_only: false,
  include_expired: false,
  sort: "score",
};

export function toQuery(f: Filters, extra: Record<string, string> = {}): string {
  const p = new URLSearchParams(extra);
  for (const [k, v] of Object.entries(f)) {
    if (v === "" || v === false) continue;
    p.set(k, String(v));
  }
  return p.toString();
}
