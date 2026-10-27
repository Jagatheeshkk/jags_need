from app.connectors.base import PortalConnector, UnverifiedPortalConnector
from app.connectors.mock import MockConnector

# Real portals stay "unverified" (no automated access) until Phase 5 confirms each one's
# officially permitted integration options and terms.
_REAL_PORTALS = [
    ("naukri", "Naukri", "https://www.naukri.com"),
    ("linkedin", "LinkedIn", "https://www.linkedin.com"),
    ("indeed", "Indeed", "https://www.indeed.com"),
    ("instahyre", "Instahyre", "https://www.instahyre.com"),
    ("cutshort", "Cutshort", "https://cutshort.io"),
]


def _build() -> dict[str, PortalConnector]:
    connectors: dict[str, PortalConnector] = {
        code: UnverifiedPortalConnector(code, name, url) for code, name, url in _REAL_PORTALS
    }
    connectors["mock"] = MockConnector()
    return connectors


_CONNECTORS = _build()


def all_connectors() -> list[PortalConnector]:
    return list(_CONNECTORS.values())


def get_connector(code: str) -> PortalConnector | None:
    return _CONNECTORS.get(code)
