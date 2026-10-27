"use client";

import { useState } from "react";
import { inputClass } from "./ui";

/** Edit a list of short strings. Enter or comma adds; duplicates (case-insensitive) are ignored. */
export function TagInput({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  label: string;
}) {
  const [draft, setDraft] = useState("");

  function add(raw: string) {
    const items = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const next = [...value];
    for (const item of items) {
      if (!next.some((v) => v.toLowerCase() === item.toLowerCase())) next.push(item);
    }
    onChange(next);
    setDraft("");
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1.5" aria-label={`${label} list`}>
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-full bg-subtle px-2.5 py-1 text-xs">
            {v}
            <button
              type="button"
              aria-label={`Remove ${v}`}
              className="text-muted hover:text-red-600"
              onClick={() => onChange(value.filter((x) => x !== v))}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <input
        aria-label={label}
        className={inputClass}
        value={draft}
        placeholder={placeholder ?? "Type and press Enter"}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            if (draft.trim()) add(draft);
          }
        }}
        onBlur={() => draft.trim() && add(draft)}
      />
    </div>
  );
}
