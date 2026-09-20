"""Operation/progress representation exposed via Temporal queries."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperationProgress:
    status: str
    step: str
    completed_steps: int
    total_steps: int
