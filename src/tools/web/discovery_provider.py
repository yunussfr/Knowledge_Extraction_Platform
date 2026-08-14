"""Global source discovery provider protocol."""

from typing import Protocol, runtime_checkable

from src.tools.web.models import DiscoveredSource


@runtime_checkable
class SourceDiscoveryProvider(Protocol):
    def search(self, query: str, *, limit: int) -> list[DiscoveredSource]:
        ...
