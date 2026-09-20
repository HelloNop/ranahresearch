"""Provider error translation. Callers catch these, never an SDK-specific exception."""


class LLMError(Exception):
    """Base for all LLM gateway errors."""


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMAuthError(LLMError):
    pass


class LLMProviderError(LLMError):
    """Any other provider-side failure (5xx, connection reset, ...)."""


class LLMInvalidResponseError(LLMError):
    """Structured output failed schema validation after retries."""
