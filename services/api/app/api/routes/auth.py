import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.api.deps import AppSettings, CurrentUser, DbSession, get_login_limiter
from app.core.config import Settings
from app.models import Notification, User
from app.schemas.auth import (
    ChangePasswordRequest,
    CsrfOut,
    LoginRequest,
    SetupRequest,
    SetupStatus,
    UserOut,
)
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.rate_limit import LoginRateLimiter
from app.security.sessions import CSRF_COOKIE, SESSION_COOKIE, issue_session, new_csrf_token
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session(response: Response, settings: Settings, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(settings.secret_key, user.id, user.session_version),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_session(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=settings.secure_cookies, httponly=True, samesite=settings.cookie_samesite
    )


def _user_exists(db: DbSession) -> bool:
    return (db.scalar(select(func.count()).select_from(User)) or 0) > 0


@router.get("/csrf", response_model=CsrfOut)
def csrf(request: Request, response: Response, settings: AppSettings) -> CsrfOut:
    token = request.cookies.get(CSRF_COOKIE) or new_csrf_token()
    # Readable by the frontend's JavaScript on purpose (double-submit pattern).
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=settings.secure_cookies,
        samesite=settings.cookie_samesite,
        path="/",
        max_age=60 * 60 * 24 * 7,
    )
    return CsrfOut(csrf_token=token)


@router.get("/setup-status", response_model=SetupStatus)
def setup_status(db: DbSession, settings: AppSettings) -> SetupStatus:
    return SetupStatus(setup_required=not _user_exists(db), bootstrap_token_required=bool(settings.bootstrap_token))


@router.post("/setup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def setup(body: SetupRequest, request: Request, response: Response, db: DbSession, settings: AppSettings) -> User:
    """Create the single owner account. Only possible while no user exists."""
    if _user_exists(db):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Owner account already exists")
    expected = settings.bootstrap_token
    if expected and not (body.bootstrap_token and hmac.compare_digest(body.bootstrap_token, expected)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token")
    user = User(
        email=body.email.lower(),
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    db.add(
        Notification(
            user_id=user.id,
            kind="system",
            title="Welcome",
            body="Complete your profile to get accurate job matches.",
            link="/profile",
        )
    )
    audit.record(db, "auth.owner_created", user_id=user.id, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    _set_session(response, settings, user)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    limiter: LoginRateLimiter = Depends(get_login_limiter),
) -> User:
    key = body.email.lower()
    retry = limiter.retry_after(key)
    if retry:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts", headers={"Retry-After": str(retry)}
        )
    user = db.scalars(select(User).where(User.email == key)).first()
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        limiter.record_failure(key)
        audit.record(db, "auth.login_failed", user_id=user.id if user else None, request=request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    limiter.reset(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    audit.record(db, "auth.login", user_id=user.id, request=request)
    db.commit()
    _set_session(response, settings, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, settings: AppSettings) -> None:
    _clear_session(response, settings)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: CurrentUser, request: Request, response: Response, db: DbSession, settings: AppSettings) -> None:
    user.session_version += 1
    audit.record(db, "auth.logout_all", user_id=user.id, request=request)
    db.commit()
    _clear_session(response, settings)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> None:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.session_version += 1  # revoke all other sessions
    audit.record(db, "auth.password_changed", user_id=user.id, request=request)
    db.commit()
    _set_session(response, settings, user)
