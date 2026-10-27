import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { CompletenessMeter } from "@/components/CompletenessMeter";
import { StatusBadge } from "@/components/StatusBadge";
import { TagInput } from "@/components/TagInput";
import type { ConnectionStatus } from "@/lib/types";

describe("StatusBadge", () => {
  it.each<[ConnectionStatus, string]>([
    ["connected", "Connected"],
    ["not_connected", "Not connected"],
    ["unsupported", "Unsupported"],
    ["needs_user_action", "Needs user action"],
    ["sleeping", "Sleeping / temporarily unavailable"],
    ["rate_limited", "Rate limited"],
    ["failed", "Failed"],
    ["succeeded", "Successfully completed"],
  ])("renders %s as '%s'", (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByTestId("status-badge")).toHaveTextContent(label);
  });
});

function Harness({ initial = [] as string[] }) {
  const [v, setV] = useState(initial);
  return (
    <>
      <TagInput label="Roles" value={v} onChange={setV} />
      <output data-testid="value">{JSON.stringify(v)}</output>
    </>
  );
}

describe("TagInput", () => {
  it("adds items on Enter and comma-separated, ignoring case-insensitive duplicates", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["QA Lead"]} />);
    const input = screen.getByLabelText("Roles");
    await user.type(input, "qa lead{Enter}");
    await user.type(input, "Test Manager, QA Manager{Enter}");
    expect(screen.getByTestId("value")).toHaveTextContent('["QA Lead","Test Manager","QA Manager"]');
  });

  it("removes an item", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["A", "B"]} />);
    await user.click(screen.getByRole("button", { name: "Remove A" }));
    expect(screen.getByTestId("value")).toHaveTextContent('["B"]');
  });
});

describe("CompletenessMeter", () => {
  it("shows score and missing items", () => {
    render(<CompletenessMeter completeness={{ score: 46, missing: ["Phone number", "Education"] }} />);
    expect(screen.getByTestId("completeness-score")).toHaveTextContent("46%");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "46");
    expect(screen.getByText("Education")).toBeInTheDocument();
  });

  it("confirms when complete", () => {
    render(<CompletenessMeter completeness={{ score: 100, missing: [] }} />);
    expect(screen.getByText("All profile checks pass.")).toBeInTheDocument();
  });
});
