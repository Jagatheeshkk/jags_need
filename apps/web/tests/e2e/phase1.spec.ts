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
