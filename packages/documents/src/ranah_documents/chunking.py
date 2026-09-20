"""Section-aware chunking.

Chunks follow section and paragraph boundaries rather than a fixed window, so
a retrieved passage is a readable unit and its page/section provenance is
exact. A size ceiling still applies for retrieval and prompt budgets; a single
paragraph over the ceiling is split at sentence boundaries, and only a single
sentence over the ceiling is ever split mid-sentence.
"""

import re
from dataclasses import dataclass

from ranah_documents.parsing import Page, ParsedDocumentResult, page_for_offset

MAX_CHUNK_TOKENS = 350
OVERLAP_TOKENS = 0

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def count_tokens(text: str) -> int:
    # ponytail: whitespace word count approximates tokens; swap in the tokenizer
    # if budgets ever need to be exact rather than conservative.
    return len(text.split())


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_index: int
    page_start: int
    page_end: int
    section_path: str
    section_type: str
    heading_text: str | None
    text: str
    token_count: int
    char_start: int
    char_end: int


def _sentence_spans(block: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    for match in _SENTENCE_END.finditer(block):
        spans.append((position, match.start()))
        position = match.end()
    spans.append((position, len(block)))
    return [(start, end) for start, end in spans if block[start:end].strip()]


def _split_words(text: str, start: int) -> list[tuple[str, int]]:
    """Last resort for a single sentence over the ceiling, which in practice
    means a mis-parsed table rather than real prose."""
    pieces: list[tuple[str, int]] = []
    words = text.split()
    cursor = 0
    for index in range(0, len(words), MAX_CHUNK_TOKENS):
        piece = " ".join(words[index : index + MAX_CHUNK_TOKENS])
        offset = text.find(piece[: min(len(piece), 40)], cursor)
        offset = offset if offset >= 0 else cursor
        pieces.append((piece, start + offset))
        cursor = offset + len(piece)
    return pieces


def _split_oversized(block: str, start: int) -> list[tuple[str, int]]:
    """Sentence-boundary split for a block that exceeds the ceiling alone."""
    pieces: list[tuple[str, int]] = []
    group: tuple[int, int] | None = None
    for span_start, span_end in _sentence_spans(block):
        if group is None:
            group = (span_start, span_end)
            continue
        if count_tokens(block[group[0] : span_end]) > MAX_CHUNK_TOKENS:
            pieces.append((block[group[0] : group[1]], start + group[0]))
            group = (span_start, span_end)
        else:
            group = (group[0], span_end)
    if group is not None:
        pieces.append((block[group[0] : group[1]], start + group[0]))

    bounded: list[tuple[str, int]] = []
    for text, offset in pieces:
        if count_tokens(text) > MAX_CHUNK_TOKENS:
            bounded.extend(_split_words(text, offset))
        else:
            bounded.append((text, offset))
    return bounded


def chunk_document(result: ParsedDocumentResult) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in result.sections:
        body = result.text[section.char_start : section.char_end]
        if not body.strip():
            continue
        for text, start in _accumulate(body, section.char_start):
            chunks.append(
                _build(
                    len(chunks),
                    text,
                    start,
                    section.path,
                    section.section_type,
                    section.heading_text,
                    result.pages,
                )
            )
    return chunks


def _accumulate(body: str, base: int) -> list[tuple[str, int]]:
    """Group consecutive paragraphs up to the token ceiling."""
    blocks: list[tuple[str, int]] = []
    offset = 0
    for raw in body.split("\n"):
        stripped = raw.strip()
        if stripped:
            blocks.append((stripped, base + offset + (len(raw) - len(raw.lstrip()))))
        offset += len(raw) + 1

    grouped: list[tuple[str, int]] = []
    current = ""
    current_start = base
    for block, start in blocks:
        if count_tokens(block) > MAX_CHUNK_TOKENS:
            if current:
                grouped.append((current, current_start))
                current = ""
            grouped.extend(_split_oversized(block, start))
            continue
        candidate = f"{current}\n{block}" if current else block
        if current and count_tokens(candidate) > MAX_CHUNK_TOKENS:
            grouped.append((current, current_start))
            current, current_start = block, start
        else:
            if not current:
                current_start = start
            current = candidate
    if current:
        grouped.append((current, current_start))
    return grouped


def _build(
    index: int,
    text: str,
    start: int,
    section_path: str,
    section_type: str,
    heading_text: str | None,
    pages: list[Page],
) -> Chunk:
    end = start + len(text)
    return Chunk(
        chunk_index=index,
        page_start=page_for_offset(pages, start),
        page_end=page_for_offset(pages, end),
        section_path=section_path,
        section_type=section_type,
        heading_text=heading_text,
        text=text,
        token_count=count_tokens(text),
        char_start=start,
        char_end=end,
    )
