"""Deterministic signals for grouping reports of the same underlying study.

This is not deduplication. Deduplication asks "are these the same publication
record?"; linking asks "do these different publications report one study?".
Both publications are always preserved (docs/DATA_MODEL.md #30, #31).

A shared trial registration number is the only signal treated as conclusive.
Everything weaker produces a candidate for the StudyLinker agent or a human,
because similar titles are exactly how distinct studies in one field look.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

# Registries accept distinct, well-formed identifier shapes; each is anchored so
# a number mentioned in prose cannot masquerade as a registration.
_REGISTRATION_PATTERNS = (
    re.compile(r"\bNCT\d{8}\b", re.IGNORECASE),
    re.compile(r"\bISRCTN\d{8}\b", re.IGNORECASE),
    re.compile(r"\bACTRN\d{14}\b", re.IGNORECASE),
    re.compile(r"\bChiCTR[-\w]*\d{6,}\b", re.IGNORECASE),
    re.compile(r"\bIRCT\d{11,}N\d+\b", re.IGNORECASE),
    re.compile(r"\bNTR\d{3,4}\b"),
    re.compile(r"\bDRKS\d{8}\b", re.IGNORECASE),
    re.compile(r"\bUMIN\d{9}\b", re.IGNORECASE),
    re.compile(r"\bPACTR\d{15,}\b", re.IGNORECASE),
)

_SAMPLE_SIZE = re.compile(
    r"\b(?:n\s*=\s*|total of\s+|recruited\s+|enrolled\s+|randomi[sz]ed\s+)(\d{2,6})\b"
    r"|\b(\d{2,6})\s+(?:participants|students|patients|subjects|individuals|respondents"
    r"|women|men|children|adults)\b",
    re.IGNORECASE,
)


class LinkTier(StrEnum):
    REGISTRATION = "REGISTRATION"
    STRONG_CANDIDATE = "STRONG_CANDIDATE"
    WEAK_CANDIDATE = "WEAK_CANDIDATE"


@dataclass(frozen=True, slots=True)
class StudyCandidate:
    work_id: str
    title: str
    abstract: str | None = None
    full_text: str | None = None
    authors: tuple[str, ...] = ()
    publication_year: int | None = None
    publication_type: str | None = None

    def searchable(self) -> str:
        return "\n".join(part for part in (self.title, self.abstract, self.full_text) if part)


@dataclass(frozen=True, slots=True)
class LinkSignal:
    work_id_a: str
    work_id_b: str
    tier: LinkTier
    registration_id: str | None
    signals: dict[str, object] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()


def find_registrations(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in _REGISTRATION_PATTERNS:
        found.update(match.group(0).upper() for match in pattern.finditer(text))
    return found


def find_sample_sizes(text: str) -> set[int]:
    return {int(match.group(1) or match.group(2)) for match in _SAMPLE_SIZE.finditer(text)}


def _normalize_author(name: str) -> str:
    parts = [part for part in re.split(r"[\s,]+", name.strip().lower()) if part]
    return parts[-1] if parts else ""


def shared_authors(a: StudyCandidate, b: StudyCandidate) -> set[str]:
    left = {_normalize_author(name) for name in a.authors} - {""}
    right = {_normalize_author(name) for name in b.authors} - {""}
    return left & right


def _is_abstract_type(candidate: StudyCandidate) -> bool:
    value = (candidate.publication_type or "").lower()
    return any(marker in value for marker in ("abstract", "proceedings", "conference"))


def find_link_signals(candidates: list[StudyCandidate]) -> list[LinkSignal]:
    """Pairwise signals, strongest first. Produces candidates, not conclusions,
    for everything short of a shared registration number."""
    registrations = {c.work_id: find_registrations(c.searchable()) for c in candidates}
    samples = {c.work_id: find_sample_sizes(c.searchable()) for c in candidates}
    signals: list[LinkSignal] = []

    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            common_registration = registrations[left.work_id] & registrations[right.work_id]
            if common_registration:
                identifier = sorted(common_registration)[0]
                signals.append(
                    LinkSignal(
                        work_id_a=left.work_id,
                        work_id_b=right.work_id,
                        tier=LinkTier.REGISTRATION,
                        registration_id=identifier,
                        signals={"registration_id": identifier},
                        evidence=(f"Both reports state trial registration {identifier}",),
                    )
                )
                continue

            authors = shared_authors(left, right)
            common_samples = samples[left.work_id] & samples[right.work_id]
            if not authors:
                continue

            detail: dict[str, object] = {
                "shared_authors": sorted(authors),
                "shared_sample_sizes": sorted(common_samples),
                "conference_abstract": _is_abstract_type(left) or _is_abstract_type(right),
            }
            evidence = [f"Shared authors: {', '.join(sorted(authors))}"]
            if common_samples:
                sizes = ", ".join(map(str, sorted(common_samples)))
                evidence.append(f"Both report the same sample size: {sizes}")
            tier = (
                LinkTier.STRONG_CANDIDATE
                if common_samples and len(authors) >= 2
                else LinkTier.WEAK_CANDIDATE
            )
            signals.append(
                LinkSignal(
                    work_id_a=left.work_id,
                    work_id_b=right.work_id,
                    tier=tier,
                    registration_id=None,
                    signals=detail,
                    evidence=tuple(evidence),
                )
            )

    order = {LinkTier.REGISTRATION: 0, LinkTier.STRONG_CANDIDATE: 1, LinkTier.WEAK_CANDIDATE: 2}
    return sorted(signals, key=lambda signal: order[signal.tier])
