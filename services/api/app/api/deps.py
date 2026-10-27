import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import User
from app.security.rate_limit import LoginRateLimiter
from app.security.sessions import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, read_session

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@lru_cache
def get_login_limiter() -> LoginRateLimiter:
    s = get_settings()
    return LoginRateLimiter(s.login_max_attempts, s.login_window_seconds)


def csrf_protect(request: Request) -> None:
    """Double-submit check for every state-changing request.

    The frontend reads the non-HttpOnly CSRF cookie and echoes it in a header. A cross-site page
    can make the browser send the cookie but cannot read it to set the header.
    """
    if request.method in _SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")


def get_current_user(request: Request, db: DbSession, settings: AppSettings) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    data = read_session(settings.secret_key, token, settings.session_max_age_seconds) if token else None
    user = db.get(User, data.user_id) if data else None
    if user is None or data is None or user.session_version != data.session_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
