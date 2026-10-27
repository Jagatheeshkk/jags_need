import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, apiUpload, BackendUnavailableError, formatDetail } from "@/lib/api";

const json = (status: number, body: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("api client", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    document.cookie = "aja_csrf=tok123; path=/";
  });
  afterEach(() => {
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("sends same-origin requests with the CSRF header on unsafe methods", async () => {
    fetchMock.mockResolvedValue(json(200, { ok: true }));
    await api("/profile", { method: "PATCH", body: { headline: "x" } });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/profile");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers["X-CSRF-Token"]).toBe("tok123");
  });

  it("does not send CSRF header on GET", async () => {
    fetchMock.mockResolvedValue(json(200, {}));
    await api("/profile");
    expect(fetchMock.mock.calls[0][1].headers["X-CSRF-Token"]).toBeUndefined();
  });

  it.each([502, 503, 504])("maps %i to BackendUnavailableError", async (status) => {
    fetchMock.mockResolvedValue(json(status, { detail: "waking up" }));
    await expect(api("/overview")).rejects.toBeInstanceOf(BackendUnavailableError);
  });

  it("maps network failures to BackendUnavailableError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("/overview")).rejects.toBeInstanceOf(BackendUnavailableError);
  });

  it("surfaces 401 as ApiError with status", async () => {
    fetchMock.mockResolvedValue(json(401, { detail: "Not authenticated" }));
    const err = (await api("/auth/me").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).not.toBeInstanceOf(BackendUnavailableError);
    expect(err.status).toBe(401);
    expect(err.message).toBe("Not authenticated");
  });

  it("uploads multipart with CSRF and no JSON content type", async () => {
    fetchMock.mockResolvedValue(json(201, { ok: true }));
    const form = new FormData();
    form.append("file", new Blob(["x"]), "cv.pdf");
    await apiUpload("/resumes/upload", form);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/resumes/upload");
    expect(init.body).toBe(form);
    expect(init.headers["X-CSRF-Token"]).toBe("tok123");
    expect(init.headers["Content-Type"]).toBeUndefined(); // browser sets the multipart boundary
  });

  it("surfaces upload validation errors", async () => {
    fetchMock.mockResolvedValue(json(422, { detail: "Only PDF and Word (.docx) resumes are accepted." }));
    await expect(apiUpload("/resumes/upload", new FormData())).rejects.toThrow("Only PDF and Word");
  });

  it("returns undefined for 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});

describe("formatDetail", () => {
  it("formats FastAPI validation errors", () => {
    expect(
      formatDetail([{ msg: "Value error, end_date cannot be before start_date", loc: ["body", "end_date"] }], "x"),
    ).toBe("end_date: Value error, end_date cannot be before start_date");
    expect(formatDetail(undefined, "fallback")).toBe("fallback");
  });
});
