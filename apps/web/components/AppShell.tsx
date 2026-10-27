"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, BackendUnavailableError } from "@/lib/api";
import type { User } from "@/lib/types";

export const NAV: { href: string; label: string; phase?: number }[] = [
  { href: "/", label: "Overview" },
  { href: "/profile", label: "My Profile" },
  { href: "/resumes", label: "Resume Library", phase: 3 },
  { href: "/jobs", label: "Job Discovery" },
  { href: "/saved", label: "Saved Jobs" },
  { href: "/applications", label: "Application Tracker", phase: 3 },
  { href: "/portals", label: "Portal Connections" },
  { href: "/sync", label: "Profile Sync", phase: 5 },
  { href: "/automation", label: "Automation Rules" },
  { href: "/approvals", label: "Approval Queue", phase: 4 },
  { href: "/notifications", label: "Notifications" },
  { href: "/settings", label: "Settings" },
  { href: "/health", label: "Free-Tier Usage & Health" },
];

const UserContext = createContext<User | null>(null);
export const useCurrentUser = () => useContext(UserContext);

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [state, setState] = useState<"loading" | "sleeping" | "ready" | "error">("loading");
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let attempt = 0; attempt < 8 && !cancelled; attempt++) {
        try {
          const me = await api<User>("/auth/me");
          if (!cancelled) {
            setUser(me);
            setState("ready");
          }
          return;
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) {
            router.replace("/login");
            return;
          }
          if (e instanceof BackendUnavailableError) {
            setState("sleeping");
            await new Promise((r) => setTimeout(r, Math.min(2000 * 2 ** attempt, 15000)));
            continue;
          }
          setState("error");
          return;
        }
      }
      if (!cancelled) setState("error");
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
  }

  if (state !== "ready" || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-sm text-muted" role="status">
        {state === "sleeping" && "The backend is waking up (free hosting sleeps when idle). This can take up to a minute…"}
        {state === "loading" && "Loading…"}
        {state === "error" && "Could not reach the backend. Check that the API is running, then reload."}
      </div>
    );
  }

  return (
    <UserContext.Provider value={user}>
      <div className="min-h-screen md:flex">
        <aside className="border-b border-line bg-panel md:sticky md:top-0 md:h-screen md:w-64 md:shrink-0 md:overflow-y-auto md:border-b-0 md:border-r">
          <div className="flex items-center justify-between px-4 py-4">
            <Link href="/" className="font-semibold">
              AI Job Agent
            </Link>
            <button className="md:hidden text-sm" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen}>
              Menu
            </button>
          </div>
          <nav className={`${menuOpen ? "block" : "hidden"} px-2 pb-4 md:block`} aria-label="Main">
            {NAV.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                    active ? "bg-brand/10 font-medium text-brand" : "hover:bg-subtle"
                  }`}
                >
                  {item.label}
                  {item.phase && <span className="text-[10px] text-muted">P{item.phase}</span>}
                </Link>
              );
            })}
            <div className="mt-4 border-t border-line px-3 pt-4 text-xs text-muted">
              <p className="truncate">{user.email}</p>
              <button onClick={logout} className="mt-2 text-brand hover:underline">
                Sign out
              </button>
            </div>
          </nav>
        </aside>
        <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
      </div>
    </UserContext.Provider>
  );
}
