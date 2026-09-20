"""Document parsing: bytes to pages, sections, and char offsets.

The parser is provider-neutral on purpose: extraction agents consume
ParsedDocumentResult, never a PDF library's objects, so the backend can be
replaced (or an OCR fallback added) without touching anything downstream.

Section detection is a heuristic over heading lines, not an assumption that
every article follows IMRaD. Raw heading text is always preserved, unmatched
headings stay as their own sections, and uncertainty is reported as warnings
rather than silently resolved.
"""

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PARSER_VERSION = "1"
MAX_HEADING_CHARS = 80
MAX_HEADING_WORDS = 10

SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ABSTRACT": ("abstract", "summary", "structured abstract"),
    "INTRODUCTION": ("introduction", "background"),
    "METHODS": (
        "methods",
        "method",
        "materials and methods",
        "methods and materials",
        "methodology",
        "study design",
        "design",
    ),
    "RESULTS": ("results", "findings"),
    "DISCUSSION": ("discussion", "limitations"),
    "CONCLUSION": ("conclusion", "conclusions", "concluding remarks"),
    "REFERENCES": ("references", "bibliography", "works cited", "literature cited"),
    "APPENDIX": ("appendix", "appendices", "supplementary material", "supporting information"),
}

_NUMBERING = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVXLCivxlc]+)[.)]?\s+")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d+(?:\s*(?:/|of)\s*\d+)?\s*$", re.IGNORECASE)


class DocumentParseError(Exception):
    """The document could not be read at all. The asset is preserved for retry."""


@dataclass(frozen=True, slots=True)
class Page:
    number: int
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class Section:
    section_type: str
    heading_text: str | None
    path: str
    char_start: int
    char_end: int


@dataclass(slots=True)
class ParsedDocumentResult:
    parser_name: str
    parser_version: str
    page_count: int
    text: str
    pages: list[Page]
    sections: list[Section]
    warnings: list[str] = field(default_factory=list)
    status: str = "PARSED"


class DocumentParser(Protocol):
    name: str
    version: str

    async def parse(self, content: bytes) -> ParsedDocumentResult: ...


def strip_running_lines(pages: list[str]) -> tuple[list[str], list[str]]:
    """Drop repeated headers/footers and standalone page numbers.

    A first or last line is treated as running furniture only when it repeats
    across at least half the pages, so a heading that happens to top one page
    is never removed.
    """
    if len(pages) < 3:
        edges: Counter[str] = Counter()
    else:
        edges = Counter()
        for page in pages:
            lines = [line.strip() for line in page.splitlines() if line.strip()]
            if not lines:
                continue
            edges[lines[0]] += 1
            if len(lines) > 1:
                edges[lines[-1]] += 1
    threshold = max(2, len(pages) // 2)
    running = {line for line, count in edges.items() if count >= threshold}

    cleaned = []
    removed = sorted(running)
    for page in pages:
        kept = []
        for line in page.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in running or _PAGE_NUMBER.match(stripped):
                continue
            kept.append(stripped)
        cleaned.append("\n".join(kept))
    return cleaned, removed


def _canonical_section(line: str) -> str | None:
    text = _NUMBERING.sub("", line).strip().rstrip(":.").strip().lower()
    for section_type, keywords in SECTION_KEYWORDS.items():
        if text in keywords:
            return section_type
    return None


def _is_heading(line: str) -> bool:
    text = line.strip()
    if not text or len(text) > MAX_HEADING_CHARS:
        return False
    was_numbered = bool(_NUMBERING.match(text))
    body = _NUMBERING.sub("", text).strip()
    if not body or len(body.split()) > MAX_HEADING_WORDS:
        return False
    if body.endswith((".", ",", ";")):
        return False
    return was_numbered or body.isupper() or body.istitle() or _canonical_section(line) is not None


def detect_sections(text: str) -> tuple[list[Section], list[str]]:
    """Split assembled document text at heading lines.

    Headings that match no known section name are kept as subsections of the
    current section, so a non-IMRaD paper keeps its real structure instead of
    being forced into one.
    """
    warnings: list[str] = []
    boundaries: list[tuple[int, int, str, str | None]] = []
    offset = 0
    for line in text.split("\n"):
        line_length = len(line)
        stripped = line.strip()
        if stripped and _is_heading(stripped):
            canonical = _canonical_section(stripped)
            boundaries.append((offset, offset + line_length, stripped, canonical))
        offset += line_length + 1

    if not boundaries:
        warnings.append("No section headings were detected; the document is one untyped section")
        return [
            Section(
                section_type="OTHER",
                heading_text=None,
                path="Document",
                char_start=0,
                char_end=len(text),
            )
        ], warnings

    sections: list[Section] = []
    if boundaries[0][0] > 0:
        sections.append(
            Section(
                section_type="FRONT_MATTER",
                heading_text=None,
                path="Front matter",
                char_start=0,
                char_end=boundaries[0][0],
            )
        )

    current_top = "OTHER"
    current_label = "Document"
    for index, (start, _, heading, canonical) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        if canonical:
            current_top = canonical
            current_label = heading
            path = heading
        else:
            path = f"{current_label} > {heading}" if current_label != "Document" else heading
        sections.append(
            Section(
                section_type=current_top,
                heading_text=heading,
                path=path,
                char_start=start,
                char_end=end,
            )
        )

    if not any(section.section_type in ("METHODS", "RESULTS") for section in sections):
        warnings.append("No Methods or Results heading was recognised; section typing is uncertain")
    return sections, warnings


class PdfParser:
    """pypdf-backed parser. Layout mode keeps multi-column reading order closer
    to the printed page; plain extraction is the fallback when it fails."""

    name = "pypdf"
    version = PARSER_VERSION

    async def parse(self, content: bytes) -> ParsedDocumentResult:
        try:
            reader = PdfReader(io.BytesIO(content))
            raw_pages = [self._page_text(page) for page in reader.pages]
        except (PdfReadError, OSError, ValueError, KeyError) as exc:
            raise DocumentParseError(f"{type(exc).__name__}: {exc}") from exc

        warnings: list[str] = []
        if not raw_pages:
            raise DocumentParseError("The document contains no pages")

        cleaned, removed = strip_running_lines(raw_pages)
        if removed:
            warnings.append(f"Removed {len(removed)} repeated header/footer line(s)")

        pages: list[Page] = []
        parts: list[str] = []
        offset = 0
        for number, page_text in enumerate(cleaned, start=1):
            parts.append(page_text)
            pages.append(
                Page(
                    number=number,
                    text=page_text,
                    char_start=offset,
                    char_end=offset + len(page_text),
                )
            )
            offset += len(page_text) + 1
        text = "\n".join(parts)

        empty = [page.number for page in pages if not page.text.strip()]
        if empty:
            # Image-only pages are reported, never silently treated as absent content.
            warnings.append(
                f"No extractable text on page(s) {', '.join(map(str, empty))}; "
                "these pages may be scanned images and are not OCR'd"
            )
        if not text.strip():
            raise DocumentParseError("No extractable text; the document may be a scan")

        sections, section_warnings = detect_sections(text)
        return ParsedDocumentResult(
            parser_name=self.name,
            parser_version=self.version,
            page_count=len(pages),
            text=text,
            pages=pages,
            sections=sections,
            warnings=[*warnings, *section_warnings],
            status="PARTIAL" if empty else "PARSED",
        )

    def _page_text(self, page: object) -> str:
        extract = getattr(page, "extract_text")
        try:
            return str(extract(extraction_mode="layout") or "")
        except Exception:
            return str(extract() or "")


def page_for_offset(pages: list[Page], offset: int) -> int:
    for page in pages:
        if page.char_start <= offset <= page.char_end:
            return page.number
    return pages[-1].number if pages else 1
