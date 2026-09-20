"""Open-access location resolution from provider metadata already on file.

Only locations a provider explicitly marks open access are returned. Crossref
`link` entries are deliberately excluded: they frequently address publisher
text-mining endpoints that require entitlements, so they contribute license
metadata here and never a download URL. No paywall is negotiated anywhere in
this package (docs/AGENT_CONTRACTS.md #32).
"""

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

from ranah_literature.models import ProviderWork


@dataclass(frozen=True, slots=True)
class OpenAccessLocation:
    provider: str
    url: str
    version: str | None
    license: str | None


def public_url(url: Any) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").rstrip(".").lower()
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        return False
    if host in {"localhost", "metadata.google.internal"} or host.endswith(
        (".localhost", ".local", ".internal")
    ):
        return False
    try:
        return ip_address(host).is_global
    except ValueError:
        return True


def _openalex_locations(work: ProviderWork) -> list[OpenAccessLocation]:
    raw = work.raw_metadata
    candidates = [raw.get("best_oa_location"), *(raw.get("locations") or [])]
    found = []
    for location in candidates:
        if not isinstance(location, dict) or not location.get("is_oa"):
            continue
        url = location.get("pdf_url")
        if not public_url(url):
            continue
        found.append(
            OpenAccessLocation(
                provider=work.provider,
                url=str(url),
                version=location.get("version"),
                license=location.get("license"),
            )
        )
    return found


def _semantic_scholar_locations(work: ProviderWork) -> list[OpenAccessLocation]:
    pdf = work.raw_metadata.get("openAccessPdf")
    if not isinstance(pdf, dict) or not public_url(pdf.get("url")):
        return []
    return [
        OpenAccessLocation(
            provider=work.provider,
            url=str(pdf["url"]),
            version=pdf.get("status"),
            license=pdf.get("license"),
        )
    ]


def resolve_locations(works: list[ProviderWork]) -> list[OpenAccessLocation]:
    """Ordered, de-duplicated open-access PDF locations across provider records."""
    resolved: list[OpenAccessLocation] = []
    for work in works:
        if work.provider == "openalex":
            resolved.extend(_openalex_locations(work))
        elif work.provider == "semantic_scholar":
            resolved.extend(_semantic_scholar_locations(work))
    seen: set[str] = set()
    unique = []
    for location in resolved:
        if location.url in seen:
            continue
        seen.add(location.url)
        unique.append(location)
    return unique


def license_metadata(works: list[ProviderWork]) -> dict[str, Any]:
    """What each provider claims about access rights, kept as reported."""
    metadata: dict[str, Any] = {}
    for work in works:
        raw = work.raw_metadata
        if work.provider == "openalex" and isinstance(raw.get("open_access"), dict):
            metadata["openalex_open_access"] = raw["open_access"]
        if work.provider == "semantic_scholar" and "isOpenAccess" in raw:
            metadata["semantic_scholar_is_open_access"] = raw["isOpenAccess"]
        if work.provider == "crossref" and raw.get("license"):
            metadata["crossref_license"] = raw["license"]
    return metadata
