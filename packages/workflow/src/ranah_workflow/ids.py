"""Workflow ID convention: human-traceable prefix + unique suffix."""

import uuid


def new_workflow_id(workflow_type: str, *scope_parts: str) -> str:
    scope = "-".join(scope_parts)
    suffix = uuid.uuid4().hex[:12]
    return f"{workflow_type}-{scope}-{suffix}" if scope else f"{workflow_type}-{suffix}"
