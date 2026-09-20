"""Passage retrieval over parsed chunks.

Agents receive the passages relevant to a question, never a whole document
(docs/AGENT_CONTRACTS.md #75, #76). Scoring is lexical: term overlap with a
section-type prior. That is weaker than embeddings but has no model dependency
and keeps retrieval auditable, which matters more than ranking finesse while
every returned passage still carries its page and section.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the to was were
    with we this these those study studies our""".split()
)


class Passage(Protocol):
    """Structural view of a DocumentChunk, so retrieval stays DB-free."""

    chunk_index: int
    page_start: int
    page_end: int
    section_path: str
    section_type: str
    text: str


@dataclass(frozen=True, slots=True)
class ScoredPassage:
    chunk_index: int
    page_start: int
    page_end: int
    section_path: str
    section_type: str
    text: str
    score: float


def terms(text: str) -> set[str]:
    return {
        word for word in _WORD.findall(text.lower()) if word not in _STOPWORDS and len(word) > 2
    }


def select_passages(
    chunks: Sequence[Passage],
    queries: Sequence[str],
    *,
    limit: int = 8,
    prefer_sections: Sequence[str] = (),
) -> list[ScoredPassage]:
    """Highest-scoring passages for the supplied queries, in document order.

    Document order is restored after ranking so the agent reads passages the way
    the paper presents them.
    """
    wanted = set()
    for query in queries:
        wanted |= terms(query)
    if not wanted:
        return []

    preferred = {section.upper() for section in prefer_sections}
    scored: list[ScoredPassage] = []
    for chunk in chunks:
        # A matching term in the bibliography names a cited paper, never a
        # finding of this one, so references are not retrievable evidence.
        if chunk.section_type == "REFERENCES":
            continue
        present = terms(chunk.text)
        overlap = wanted & present
        if not overlap:
            continue
        score = len(overlap) / len(wanted)
        if chunk.section_type in preferred:
            score += 0.25
        if score > 0:
            scored.append(
                ScoredPassage(
                    chunk_index=chunk.chunk_index,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_path=chunk.section_path,
                    section_type=chunk.section_type,
                    text=chunk.text,
                    score=round(score, 4),
                )
            )
    top = sorted(scored, key=lambda passage: (-passage.score, passage.chunk_index))[:limit]
    return sorted(top, key=lambda passage: passage.chunk_index)
