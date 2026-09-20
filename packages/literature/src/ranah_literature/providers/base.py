"""AcademicProvider interface. Business logic never imports a concrete provider directly."""

from abc import ABC, abstractmethod

from ranah_literature.errors import UnsupportedCapabilityError
from ranah_literature.models import ProviderCapability, ProviderWork, SearchPage, SearchRequest


class AcademicProvider(ABC):
    name: str
    capabilities: ProviderCapability

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchPage: ...

    @abstractmethod
    async def get_work(self, provider_id: str) -> ProviderWork: ...

    @abstractmethod
    async def get_by_doi(self, doi: str) -> ProviderWork | None: ...

    async def get_references(self, provider_id: str) -> list[ProviderWork]:
        if not self.capabilities.can_get_references:
            raise UnsupportedCapabilityError(f"{self.name} does not support get_references")
        raise NotImplementedError

    async def get_citations(self, provider_id: str) -> list[ProviderWork]:
        if not self.capabilities.can_get_citations:
            raise UnsupportedCapabilityError(f"{self.name} does not support get_citations")
        raise NotImplementedError
