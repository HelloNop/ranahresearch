"""Versioned prompt loading. Prompts live in files, never as giant strings in business logic."""

import os
from pathlib import Path


class PromptNotFoundError(Exception):
    pass


def load_prompt(name: str, version: str, *, base_dir: Path | None = None) -> str:
    """Reads prompts/<name>/<version>.md, e.g. prompts/sample_agent/v1.md."""
    root = base_dir or Path(os.environ.get("RANAH_PROMPTS_DIR", "prompts"))
    path = root / name / f"{version}.md"
    if not path.is_file():
        raise PromptNotFoundError(f"no prompt at {path}")
    return path.read_text()
