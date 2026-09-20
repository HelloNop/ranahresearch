"""Default activity retry policy. Per docs/TECHNICAL_ARCHITECTURE.md #89:
retry transient network/429/5xx/timeouts; do not retry validation/permission failures.
"""

from datetime import timedelta

from temporalio.common import RetryPolicy

from ranah_workflow.errors import NonRetryableActivityError

DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
    non_retryable_error_types=[NonRetryableActivityError.__name__],
)
