"""Deployment readiness check: flags misconfiguration and any dependency that would cost money."""

import urllib.request
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.settings import ReadinessCheck, ReadinessReport
from app.services import usage

# Hosts we know about, with the caveat recorded in docs/free-tier-audit.md.
_DB_HOSTS: list[tuple[str, Literal["ok", "warn"], str]] = [
    ("neon.tech", "ok", "Neon Free plan: no expiry; compute suspends after 5 min idle; 1 GB storage per project."),
    ("supabase.co", "warn", "Supabase Free: projects pause after ~1 week of inactivity; keep backups."),
    ("supabase.com", "warn", "Supabase Free: projects pause after ~1 week of inactivity; keep backups."),
    ("render.com", "warn", "Render free Postgres expires 30 days after creation. Do not use for permanent data."),
]


def _check_database(db: Session, settings: Settings) -> ReadinessCheck:
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - report any connectivity failure
        return ReadinessCheck(
            name="database", status="fail", detail="Database unreachable (it may be waking up from idle suspend)."
        )
    if settings.is_sqlite:
        status = "fail" if settings.environment == "production" else "info"
        return ReadinessCheck(name="database", status=status, detail="SQLite (local development/tests only).")
    host = urlparse(settings.database_url.replace("+psycopg", "")).hostname or ""
    if host in {"localhost", "127.0.0.1", "db"}:
        return ReadinessCheck(name="database", status="ok", detail="Local PostgreSQL (Docker).")
    for suffix, status, detail in _DB_HOSTS:
        if host.endswith(suffix):
            return ReadinessCheck(name="database", status=status, detail=detail)
    return ReadinessCheck(
        name="database", status="warn", detail="Unrecognised PostgreSQL host: confirm it is on a genuinely free plan."
    )


def _check_ai(settings: Settings) -> ReadinessCheck:
    if settings.ai_provider == "rule_based":
        return ReadinessCheck(
            name="ai_engine", status="ok", detail="Rule-based engine: no API key, no network, no cost."
        )
    try:
        host = urlparse(settings.ollama_base_url).hostname
        if host not in {"localhost", "127.0.0.1", "ollama", "host.docker.internal"}:
            return ReadinessCheck(
                name="ai_engine",
                status="warn",
                detail="OLLAMA_BASE_URL is not local; a remote model host may cost money.",
            )
        with urllib.request.urlopen(f"{settings.ollama_base_url}/api/tags", timeout=2):  # noqa: S310
            pass
        return ReadinessCheck(name="ai_engine", status="ok", detail="Local Ollama reachable.")
    except OSError:
        return ReadinessCheck(
            name="ai_engine", status="warn", detail="Ollama not reachable; the rule-based engine will be used instead."
        )


def run(db: Session, settings: Settings) -> ReadinessReport:
    checks = [
        _check_database(db, settings),
        _check_ai(settings),
        ReadinessCheck(
            name="email",
            status="info",
            detail="Email disabled. In-app notifications and downloadable digests are used.",
        ),
        ReadinessCheck(
            name="file_storage",
            status="ok",
            detail="Resumes are stored in PostgreSQL; no object storage service required.",
        ),
        ReadinessCheck(
            name="background_jobs",
            status="info",
            detail="Database-backed tasks; free hosting may sleep, so use manual refresh.",
        ),
    ]
    storage = usage.report(db, settings)
    checks.append(ReadinessCheck(name="database_storage", status=storage["status"], detail=storage["detail"]))
    prod = settings.environment == "production"
    checks.append(
        ReadinessCheck(
            name="cookies",
            status="ok" if settings.secure_cookies or not prod else "fail",
            detail="Secure cookies enabled." if settings.secure_cookies else "Secure cookies off (dev only).",
        )
    )
    checks.append(
        ReadinessCheck(
            name="bootstrap_token",
            status="ok" if settings.bootstrap_token else ("fail" if prod else "info"),
            detail="Owner setup is protected by BOOTSTRAP_TOKEN."
            if settings.bootstrap_token
            else "No BOOTSTRAP_TOKEN: anyone reaching the API first could create the owner account.",
        )
    )
    # Every configurable provider is restricted to free options by Settings validation,
    # so this list stays empty unless a future integration adds a paid one.
    paid: list[str] = []
    ready = not any(c.status == "fail" for c in checks) and not paid
    return ReadinessReport(ready=ready, paid_dependencies=paid, checks=checks)
