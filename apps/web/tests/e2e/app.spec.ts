import { expect, test, type Page } from "@playwright/test";

// Synthetic test identity; never a real account.
const EMAIL = "e2e-owner@example.com";
const PASSWORD = "e2e passphrase for testing only";

test.describe.configure({ mode: "serial" });

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
});

test.afterAll(async () => {
  await page.close();
});

test("unauthenticated visitor is sent to owner setup", async () => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Create owner account" })).toBeVisible();
});

test("owner account setup lands on the overview with real counts", async () => {
  await page.getByLabel("Display name").fill("E2E Owner");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  // Seeded synthetic jobs are reported separately from real ones (none).
  await expect(page.getByText("Real job listings").locator("..")).toContainText("0");
  await expect(page.getByText("Synthetic sample jobs").locator("..")).toContainText("11");
});

test("profile edits persist", async () => {
  await page.getByRole("link", { name: "My Profile" }).click();
  await page.getByLabel("Professional headline").fill("QA Lead | Functional and Automation Testing");
  await page.getByLabel("Preferred roles", { exact: true }).fill("QA Lead");
  await page.getByLabel("Preferred roles", { exact: true }).press("Enter");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Professional headline")).toHaveValue("QA Lead | Functional and Automation Testing");
  await expect(page.getByLabel("Preferred roles list")).toContainText("QA Lead");
});

test("employment entry can be added and invalid dates are rejected", async () => {
  await page.getByRole("button", { name: "Add employment" }).click();
  await page.getByLabel("Job title").fill("Test Lead");
  await page.getByLabel("Company").fill("Example Synthetic Co");
  await page.getByLabel("Start date").fill("2019-04-01");
  await page.getByLabel("End date").fill("2018-01-01");
  await page.getByRole("button", { name: "Add entry" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "end_date cannot be before start_date" })).toBeVisible();

  await page.getByLabel("End date").fill("2023-03-31");
  await page.getByRole("button", { name: "Add entry" }).click();
  await expect(page.getByText("Test Lead · Example Synthetic Co")).toBeVisible();
});

test("real portals are shown as unsupported; mock connects", async () => {
  await page.getByRole("link", { name: "Portal Connections" }).click();
  const linkedin = page.locator("section", { hasText: "LinkedIn" });
  await expect(linkedin.getByTestId("status-badge")).toHaveText("Unsupported");
  const mock = page.locator("section", { hasText: "Mock Portal" });
  await expect(mock.getByTestId("status-badge")).toHaveText("Not connected");
  await mock.getByRole("button", { name: "Check status" }).click();
  await expect(mock.getByTestId("status-badge")).toHaveText("Connected");
});

test("job discovery lists scored, labelled synthetic jobs", async () => {
  await page.getByRole("link", { name: "Job Discovery" }).click();
  // First visit triggers the scheduled refresh; its summary appears once done.
  await expect(page.getByText(/Last refresh .*fetched/)).toBeVisible();
  await expect(page.getByTestId("job-total")).toBeVisible();
  const cards = page.locator("section", { has: page.locator("h3") });
  const count = await cards.count();
  expect(count).toBeGreaterThan(0);
  await expect(page.getByText("Synthetic sample", { exact: true })).toHaveCount(count);
  await expect(page.getByTestId("score")).toHaveCount(count);
  await expect(page.getByRole("link", { name: "Download digest" })).toHaveAttribute("href", "/api/jobs/digest");
});

test("filters narrow the list", async () => {
  await page.getByRole("combobox", { name: "Work arrangement", exact: true }).selectOption("remote");
  await page.getByRole("button", { name: "Apply filters" }).click();
  const cards = page.locator("section", { has: page.locator("h3") });
  await expect(cards.first()).toContainText("remote");
  for (const text of await cards.allInnerTexts()) expect(text).toContain("remote");
  await page.getByRole("button", { name: "Reset" }).click();
});

test("job details explain the score, and saving shows it under Saved Jobs", async () => {
  const first = page.locator("section h3 a").first();
  const title = (await first.innerText()).trim();
  await first.click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why this score" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Skills and experience" })).toBeVisible();
  await expect(page.getByText("not a real opening")).toBeVisible();
  await page.getByRole("button", { name: "☆ Save" }).click();
  await expect(page.getByRole("button", { name: "★ Saved" })).toBeVisible();
  await page.getByRole("button", { name: "Good match" }).click();
  await expect(page.getByText("feedback saved")).toBeVisible();

  await page.getByRole("link", { name: "Saved Jobs" }).click();
  await expect(page.getByRole("heading", { name: "Saved Jobs", level: 1 })).toBeVisible();
  await expect(page.locator("main section h3 a:visible")).toHaveText([title]);
});

test("resume upload is read, reviewed and only ticked values are applied", async () => {
  await page.getByRole("link", { name: "Resume Library" }).click();
  await page.getByLabel("Resume file").setInputFiles("tests/e2e/fixtures/synthetic-resume.docx");
  await page.getByRole("button", { name: "Upload and read" }).click();
  await expect(page.getByRole("heading", { name: "Review what was read from your resume" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "asha.example@example.com" })).toBeVisible();
  await page.getByLabel("Use Phone").check();
  await page.getByRole("checkbox", { name: "Playwright", exact: true }).check();
  await page.getByRole("button", { name: "Copy ticked values to profile" }).click();
  await expect(page.getByText("Selected values copied to your profile.")).toBeVisible();
  await page.getByRole("link", { name: "My Profile" }).click();
  await expect(page.getByLabel("Phone", { exact: true })).toHaveValue("+91 98765 43210");
  await expect(page.getByLabel("Full name", { exact: true })).toHaveValue("E2E Owner"); // not ticked, not changed
});

test("master resume generates versioned DOCX and PDF downloads", async () => {
  await page.getByRole("link", { name: "Resume Library" }).click();
  await page.getByRole("button", { name: "Generate master resume" }).click();
  await expect(page.getByText(/Master resume v1 generated/)).toBeVisible();
  const row = page.getByRole("row", { name: /Master resume/ });
  for (const [fmt, type] of [["DOCX", "wordprocessingml"], ["PDF", "application/pdf"]]) {
    const href = await row.getByRole("link", { name: fmt }).getAttribute("href");
    const res = await page.request.get(href!);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain(type);
  }
});

test("prepare an application and track a simulated submission", async () => {
  await page.getByRole("link", { name: "Saved Jobs" }).click();
  await page.locator("main section h3 a:visible").first().click();
  await page.getByRole("button", { name: "Generate tailored resume" }).click();
  await expect(page.getByText(/Tailored resume v1 created/)).toBeVisible();
  await page.getByRole("button", { name: "Write cover letter" }).click();
  await expect(page.getByText(/Cover letter v1 created/)).toBeVisible();
  await page
    .getByLabel("Screening questions")
    .fill(["What is your expected CTC?", "Are you legally authorized to work in India?"].join("\n"));
  await page.getByRole("button", { name: "Draft answers" }).click();
  await expect(page.getByText(/Review: Legal declaration/)).toBeVisible();
  await page.getByRole("button", { name: "Add to tracker" }).click();
  await expect(page.getByText("Status:")).toContainText("draft");

  await page.getByRole("link", { name: "Open in tracker" }).click();
  await expect(page.getByRole("heading", { name: "Application Tracker", level: 1 })).toBeVisible();
  const card = page.locator("main section:visible").filter({ has: page.getByTestId("app-status") }).first();
  await expect(card.getByTestId("app-status")).toHaveText("Draft");
  await card.getByRole("button", { name: "Run simulated submission" }).click();
  await expect(card.getByTestId("app-status")).toHaveText("Submitted");
  await expect(card.getByText("Simulated submission")).toBeVisible();
  await expect(card.getByText(/Reference MOCK-/)).toBeVisible();
  await card.getByRole("button", { name: "History" }).click();
  await expect(card.getByText(/submission → Submitted \(simulated\)/)).toBeVisible();
});

test("automation is off and paused by default", async () => {
  await page.getByRole("link", { name: "Automation Rules" }).click();
  await expect(page.getByLabel("Automation enabled")).not.toBeChecked();
  await expect(page.getByLabel("Global pause (overrides everything)")).toBeChecked();
});

test("readiness reports no paid dependencies", async () => {
  await page.getByRole("link", { name: "Free-Tier Usage & Health" }).click();
  await expect(page.getByText("Paid dependencies:")).toContainText("none");
});

test("sign out then sign back in", async () => {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/profile");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill("wrong password!!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Invalid email or password" })).toBeVisible();
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});
