import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JobCard, salaryText, ScoreBadge } from "@/components/JobBits";
import { DEFAULT_FILTERS, toQuery } from "@/lib/jobs";
import type { JobSummary } from "@/lib/types";

const job: JobSummary = {
  id: "j1",
  title: "QA Lead",
  company: "Example HR Cloud (Synthetic)",
  location: "Bengaluru",
  work_arrangement: "hybrid",
  salary_min: null,
  salary_max: null,
  salary_currency: null,
  experience_min: 8,
  experience_max: 12,
  posted_at: null,
  expires_at: null,
  last_seen_at: null,
  status: "active",
  freshness: "new",
  is_synthetic: true,
  source_count: 2,
  match: {
    score: 87.4,
    matched_skills: ["Playwright", "UAT"],
    missing_skills: ["test strategy"],
    eligibility: { status: "ineligible", reasons: ["Requires 12+ years."] },
    components: {},
    engine: "rule_based/1",
    is_saved: false,
    feedback: null,
  },
};

describe("toQuery", () => {
  it("omits empty and false filters", () => {
    expect(toQuery(DEFAULT_FILTERS)).toBe("sort=score");
    expect(toQuery({ ...DEFAULT_FILTERS, role: "lead", eligible_only: true, min_score: "60" }, { limit: "100" })).toBe(
      "limit=100&role=lead&min_score=60&eligible_only=true&sort=score",
    );
  });
});

describe("ScoreBadge", () => {
  it("rounds and handles missing scores", () => {
    const { rerender } = render(<ScoreBadge score={87.4} />);
    expect(screen.getByTestId("score")).toHaveTextContent("87");
    rerender(<ScoreBadge score={null} />);
    expect(screen.getByText("Not scored")).toBeInTheDocument();
  });
});

describe("JobCard", () => {
  it("labels synthetic data, eligibility, duplicates and skills", () => {
    render(<JobCard job={job} />);
    expect(screen.getByText("Synthetic sample")).toBeInTheDocument();
    expect(screen.getByText("Not eligible")).toHaveAttribute("title", "Requires 12+ years.");
    expect(screen.getByText(/Seen on 2 sources/)).toBeInTheDocument();
    expect(screen.getByText(/Playwright, UAT/)).toBeInTheDocument();
    expect(screen.getByText(/Missing: test strategy/)).toBeInTheDocument();
    expect(screen.getByText("Salary not disclosed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "QA Lead" })).toHaveAttribute("href", "/jobs/j1");
  });
});

describe("salaryText", () => {
  it("formats partial ranges", () => {
    expect(salaryText({ salary_min: 2000000, salary_max: null, salary_currency: "INR" })).toBe("INR 20,00,000 – ?");
  });
});
