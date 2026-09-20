"""Provider error translation. Callers catch these, never an httpx/SDK-specific exception."""


class ProviderError(Exception):
    """Base for all academic-provider errors."""


class ProviderTimeoutError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderNotFoundError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    """Any other provider-side failure (5xx, malformed body, connection reset, ...)."""


class UnsupportedCapabilityError(ProviderError):
    """Raised when calling an optional operation a provider does not declare support for."""
