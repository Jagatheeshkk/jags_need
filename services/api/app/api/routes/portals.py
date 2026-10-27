from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.connectors.base import ConnectorNotSupported, JobFilters, PortalJob
from app.connectors.registry import get_connector
from app.services import portal_service
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
