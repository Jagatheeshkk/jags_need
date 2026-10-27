"""Normalisation helpers for job records from any source.

Job text comes from third parties and is treated as untrusted data: it is cleaned and length
limited, stored as plain text, and never interpreted as instructions.
"""

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_TITLE = 300
MAX_DESCRIPTION = 20_000

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_COMPANY_SUFFIXES = {
    "ltd",
    "limited",
    "pvt",
    "private",
    "inc",
    "llc",
    "llp",
    "corp",
    "corporation",
    "co",
    "plc",
    "gmbh",
}
_TRACKING_PARAMS = re.compile(r"^(utm_.*|ref|refid|src|source|trk|trackingid|fbclid|gclid|mc_.*)$", re.I)
_WORD = re.compile(r"[a-z0-9+#.]+")


def clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", value)
    text = _CONTROL.sub("", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:limit] or None


def company_key(name: str) -> str:
    """'Example HR Cloud Pvt. Ltd.' -> 'example hr cloud'."""
    words = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()
    while words and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def canonical_url(url: str | None) -> str | None:
    """Lower-case scheme/host, drop fragments, tracking parameters and trailing slashes."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower().removeprefix("www.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k)))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, query, ""))[:1000]


def tokens(text: str | None) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def shingles(text: str | None, size: int = 3) -> set[str]:
    words = _WORD.findall((text or "").lower())
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def content_hash(title: str, company: str, location: str | None, description: str | None) -> str:
    norm = "|".join(" ".join((x or "").lower().split()) for x in (title, company, location, description))
    return hashlib.sha256(norm.encode()).hexdigest()


Freshness = Literal["new", "fresh", "aging", "stale", "expired", "unknown"]


def as_utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; everything is stored in UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def freshness(
    posted_at: datetime | None, expires_at: datetime | None, status: str = "active", now: datetime | None = None
) -> Freshness:
    now = now or datetime.now(UTC)
    if status == "expired" or (expires_at is not None and as_utc(expires_at) <= now):
        return "expired"
    if posted_at is None:
        return "unknown"
    age_days = (now - as_utc(posted_at)).total_seconds() / 86400
    if age_days < 3:
        return "new"
    if age_days < 14:
        return "fresh"
    if age_days < 30:
        return "aging"
    return "stale"
