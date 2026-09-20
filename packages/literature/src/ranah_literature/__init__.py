"""Provider-neutral academic literature interface. All provider access goes through
AcademicProvider (see docs/TECHNICAL_ARCHITECTURE.md #23)."""

from ranah_literature.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    UnsupportedCapabilityError,
)
from ranah_literature.models import (
    ProviderAuthor,
    ProviderCapability,
    ProviderIdentifier,
    ProviderIdentifierType,
    ProviderWork,
    SearchPage,
    SearchRequest,
)
from ranah_literature.providers.base import AcademicProvider

__all__ = [
    "AcademicProvider",
    "ProviderAuthError",
    "ProviderAuthor",
    "ProviderCapability",
    "ProviderError",
    "ProviderIdentifier",
    "ProviderIdentifierType",
    "ProviderNotFoundError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderWork",
    "SearchPage",
    "SearchRequest",
    "UnsupportedCapabilityError",
]
