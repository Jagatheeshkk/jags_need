from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.connectors.base import ConnectorNotSupported, JobFilters, ManualPortalConnector, PortalJob
from app.connectors.registry import get_connector
from app.services import portal_service, profile_service
from app.services.portal_service import PortalOut

router = APIRouter(prefix="/portals", tags=["portals"])


@router.get("", response_model=list[PortalOut])
def list_portals(user: CurrentUser, db: DbSession) -> list[PortalOut]:
    return portal_service.list_for_user(db, user)


@router.post("/{code}/check", response_model=PortalOut)
def check_portal(code: str, user: CurrentUser, db: DbSession) -> PortalOut:
    result = portal_service.check_connection(db, user, code)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown portal")
    return result


@router.post("/{code}/search", response_model=list[PortalJob])
def search(code: str, filters: JobFilters, user: CurrentUser) -> list[PortalJob]:
    """Search one portal. Only connectors whose search capability is verified will run."""
    connector = get_connector(code)
    if connector is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown portal")
    try:
        return connector.search_jobs(filters)
    except ConnectorNotSupported as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


class SearchLink(BaseModel):
    portal: str
    url: str
    keywords: str
    location: str | None


@router.get("/{code}/search-link", response_model=SearchLink)
def search_link(
    code: str,
    user: CurrentUser,
    db: DbSession,
    keywords: str | None = Query(None, max_length=200),
    location: str | None = Query(None, max_length=200),
) -> SearchLink:
    """A link to the portal's own job search, for the user to open in their browser.

    Defaults to the first preferred role and location from the profile. The server never requests it.
    """
    connector = get_connector(code)
    if not isinstance(connector, ManualPortalConnector):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Search links exist only for real portals")
    profile = profile_service.get_or_create(db, user)
    kw = keywords or (profile.preferred_roles[0] if profile.preferred_roles else "QA Lead")
    loc = (
        location
        if location is not None
        else next((x for x in profile.preferred_locations if x.lower() != "remote"), profile.location)
    )
    return SearchLink(portal=code, url=connector.search_url(kw, loc), keywords=kw, location=loc)
