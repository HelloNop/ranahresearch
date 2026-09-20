"""Activity error taxonomy. Workflows retry based on error type, not error message."""


class NonRetryableActivityError(Exception):
    """Invalid input, permission denied, or a scientific validation failure: retrying won't help."""


class TransientActivityError(Exception):
    """Network blip, timeout, or provider 429/5xx: safe to retry."""
