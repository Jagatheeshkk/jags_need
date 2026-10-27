"""Stateless signed session cookies.

The cookie holds only {user id, session version}, signed and timestamped with SECRET_KEY.
Nothing session-related is stored in the database; bumping users.session_version revokes
every cookie issued before (logout-all, password change).
"""

import secrets
import uuid
from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "aja_session"
CSRF_COOKIE = "aja_csrf"
CSRF_HEADER = "x-csrf-token"


@dataclass(frozen=True)
class SessionData:
    user_id: uuid.UUID
    session_version: int


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="aja.session.v1")


def issue_session(secret_key: str, user_id: uuid.UUID, session_version: int) -> str:
    return _serializer(secret_key).dumps({"uid": str(user_id), "sv": session_version})


def read_session(secret_key: str, token: str, max_age: int) -> SessionData | None:
    try:
        data = _serializer(secret_key).loads(token, max_age=max_age)
        return SessionData(user_id=uuid.UUID(data["uid"]), session_version=int(data["sv"]))
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
