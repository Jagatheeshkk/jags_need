from app.connectors.base import ManualPortalConnector, PortalConnector
from app.connectors.mock import MockConnector
from app.connectors.policies import POLICIES

# Real portals are manual-only: Phase 5 verified that none of them permits automated access
# for job seekers (see connectors/policies.py and docs/portal-integrations.md).


def _build() -> dict[str, PortalConnector]:
    connectors: dict[str, PortalConnector] = {code: ManualPortalConnector(p) for code, p in POLICIES.items()}
    connectors["mock"] = MockConnector()
    return connectors


_CONNECTORS = _build()


def all_connectors() -> list[PortalConnector]:
    return list(_CONNECTORS.values())


def get_connector(code: str) -> PortalConnector | None:
    return _CONNECTORS.get(code)
