// Browser-side API client. All calls go to same-origin /api/*, which Next.js rewrites to the
// FastAPI backend, so session cookies stay first-party and HttpOnly.

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Backend asleep, restarting, or database waking up (free-tier cold start). */
export class BackendUnavailableError extends ApiError {
  constructor(message = "The backend is waking up or temporarily unavailable.") {
    super(message, 503, "backend_unavailable");
    this.name = "BackendUnavailableError";
  }
}

const CSRF_COOKIE = "aja_csrf";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function csrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  const data = await api<{ csrf_token: string }>("/auth/csrf");
  return data.csrf_token;
}

type Detail = string | { msg: string; loc?: (string | number)[] }[] | undefined;

export function formatDetail(detail: Detail, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  return detail
    .map((d) => {
      const field = d.loc?.filter((p) => p !== "body").join(".");
      return field ? `${field}: ${d.msg}` : d.msg;
    })
    .join("; ");
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) headers["X-CSRF-Token"] = await csrfToken();

  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new BackendUnavailableError();
  }

  if ([502, 503, 504].includes(res.status)) {
    let msg: string | undefined;
    try {
      msg = (await res.json()).detail;
    } catch {
      /* proxy error page, not JSON */
    }
    throw new BackendUnavailableError(typeof msg === "string" ? msg : undefined);
  }
  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => undefined);
  if (!res.ok) {
    throw new ApiError(formatDetail(data?.detail, `Request failed (${res.status})`), res.status, data?.code);
  }
  return data as T;
}
