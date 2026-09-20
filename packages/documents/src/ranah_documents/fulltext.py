"""Full-text acquisition: resolve, fetch, verify, hash, store, record.

This module never parses. Parsing is a separate stage with its own provenance
(EPIC-024). No access control is ever circumvented here: remote fetching is
limited to locations a provider explicitly marks open access.
"""

import asyncio
import hashlib
import ipaddress
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from ranah_domain.enums import (
    FullTextAcquisitionStatus,
    FullTextAssetStatus,
    FullTextSourceType,
)
from ranah_domain.models.fulltext import FullTextAcquisition, FullTextAsset
from ranah_domain.models.search import SearchResult, SearchRun
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord
from ranah_domain.storage import ObjectStorage
from ranah_literature.models import ProviderWork
from ranah_literature.open_access import (
    OpenAccessLocation,
    license_metadata,
    public_url,
    resolve_locations,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_ASSET_BYTES = 50 * 1024 * 1024
PDF_MAGIC = b"%PDF-"
DOWNLOAD_TIMEOUT_SECONDS = 30.0

Scanner = Callable[[bytes], Awaitable[None]]


class FullTextRejected(Exception):
    """Content that must not be stored: wrong type, oversized, or scanner refusal."""


async def _no_scan(content: bytes) -> None:
    # ponytail: no malware scanner is deployed yet; swap this hook for the real
    # scanner call when one exists (docs/TECHNICAL_ARCHITECTURE.md #71).
    return None


def validate_pdf(content: bytes) -> None:
    if not content:
        raise FullTextRejected("The file is empty")
    if len(content) > MAX_ASSET_BYTES:
        raise FullTextRejected(f"The file exceeds the {MAX_ASSET_BYTES // (1024 * 1024)}MB limit")
    if not content.startswith(PDF_MAGIC):
        raise FullTextRejected("The content is not a PDF")


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def storage_key(project_id: uuid.UUID, work_id: uuid.UUID, digest: str) -> str:
    """Content-addressed, tenant-scoped, and free of caller-supplied filenames."""
    return f"projects/{project_id}/works/{work_id}/full-text/{digest}.pdf"


async def fetch(url: str, client: httpx.AsyncClient, *, check_dns: bool = True) -> bytes:
    """Size-capped streaming download. The cap is enforced while reading, so an
    oversized or endless response never lands in memory whole."""
    if not public_url(url):
        raise FullTextRejected("The open-access URL is not a public HTTP address")
    if check_dns:
        host = httpx.URL(url).host
        try:
            addresses = await asyncio.to_thread(socket.getaddrinfo, host, None)
        except OSError as exc:
            raise FullTextRejected("The open-access host cannot be resolved") from exc
        if not addresses or any(
            not ipaddress.ip_address(address[4][0]).is_global for address in addresses
        ):
            raise FullTextRejected("The open-access host resolves to a non-public address")
    chunks: list[bytes] = []
    total = 0
    async with client.stream(
        "GET", url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=False
    ) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MAX_ASSET_BYTES:
                raise FullTextRejected("The remote file exceeds the size limit")
            chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    status: FullTextAcquisitionStatus
    asset_id: uuid.UUID | None
    attempts: list[dict[str, Any]]
    error: str | None


class FullTextAcquisitionService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        *,
        client: httpx.AsyncClient | None = None,
        scan: Scanner = _no_scan,
    ) -> None:
        self._session = session
        self._storage = storage
        self._client = client
        self._scan = scan

    async def provider_records(self, work: WorkRecord) -> list[ProviderWork]:
        """The provider payloads captured for this work during discovery."""
        provider_ids = await self._session.scalars(
            select(WorkMetadataObservation).where(
                WorkMetadataObservation.work_id == work.id,
                WorkMetadataObservation.field_name == "provider_record_id",
            )
        )
        wanted = {(row.provider, str(row.field_value.get("value"))) for row in provider_ids}
        if not wanted:
            return []
        payloads = await self._session.scalars(
            select(SearchResult.normalized_payload)
            .join(SearchRun)
            .where(SearchRun.project_id == work.project_id)
            .order_by(SearchResult.id)
        )
        records: dict[tuple[str, str], ProviderWork] = {}
        for payload in payloads:
            record = ProviderWork.model_validate(payload)
            key = (record.provider, record.provider_id)
            if key in wanted:
                records[key] = record
        return list(records.values())

    async def _acquisition_row(self, work: WorkRecord) -> FullTextAcquisition:
        row = await self._session.scalar(
            select(FullTextAcquisition).where(
                FullTextAcquisition.project_id == work.project_id,
                FullTextAcquisition.work_id == work.id,
            )
        )
        if row is None:
            row = FullTextAcquisition(project_id=work.project_id, work_id=work.id)
            self._session.add(row)
            await self._session.flush()
        return row

    async def _store_asset(
        self,
        work: WorkRecord,
        content: bytes,
        *,
        source_type: FullTextSourceType,
        source_url: str | None,
        uploaded_by: uuid.UUID | None,
        license_data: dict[str, Any],
    ) -> tuple[FullTextAsset, bool]:
        """Content-addressed: the same bytes for the same work reuse the stored
        object and the existing row rather than accumulating duplicate blobs.
        Returns the asset and whether this call created it."""
        validate_pdf(content)
        await self._scan(content)
        digest = content_hash(content)
        existing = await self._session.scalar(
            select(FullTextAsset).where(
                FullTextAsset.work_id == work.id, FullTextAsset.sha256 == digest
            )
        )
        if existing is not None:
            if existing.status == FullTextAssetStatus.REMOVED:
                existing.status = FullTextAssetStatus.AVAILABLE
            return existing, False
        key = storage_key(work.project_id, work.id, digest)
        await self._storage.put(key, content, "application/pdf")
        asset = FullTextAsset(
            project_id=work.project_id,
            work_id=work.id,
            storage_key=key,
            source_type=source_type,
            source_url=source_url,
            mime_type="application/pdf",
            byte_size=len(content),
            sha256=digest,
            status=FullTextAssetStatus.AVAILABLE,
            retrieved_at=datetime.now(UTC),
            uploaded_by=uploaded_by,
            license_metadata=license_data,
        )
        self._session.add(asset)
        await self._session.flush()
        return asset, True

    async def upload(
        self, work: WorkRecord, content: bytes, *, uploaded_by: uuid.UUID
    ) -> tuple[FullTextAsset, bool]:
        asset, created = await self._store_asset(
            work,
            content,
            source_type=FullTextSourceType.USER_UPLOAD,
            source_url=None,
            uploaded_by=uploaded_by,
            license_data={"provided_by": "USER_UPLOAD"},
        )
        row = await self._acquisition_row(work)
        row.status = FullTextAcquisitionStatus.AVAILABLE
        row.error = None
        row.last_attempt_at = datetime.now(UTC)
        # The upload event is recorded even when the bytes were already on file,
        # so a repeated upload stays auditable without storing a second blob.
        row.attempts = [
            *row.attempts,
            {
                "source_type": FullTextSourceType.USER_UPLOAD.value,
                "outcome": "STORED" if created else "DEDUPLICATED",
                "sha256": asset.sha256,
                "uploaded_by": str(uploaded_by),
                "at": datetime.now(UTC).isoformat(),
            },
        ]
        return asset, created

    async def acquire(self, work: WorkRecord) -> AcquisitionOutcome:
        """Try every open-access location on file, in order, and record what
        each attempt actually produced."""
        row = await self._acquisition_row(work)
        row.status = FullTextAcquisitionStatus.SEARCHING
        records = await self.provider_records(work)
        locations = resolve_locations(records)
        licenses = license_metadata(records)
        attempts: list[dict[str, Any]] = []
        asset: FullTextAsset | None = None
        client = self._client or httpx.AsyncClient(follow_redirects=False)
        try:
            for location in locations:
                record, attempted = await self._attempt(work, location, licenses, client)
                attempts.append(record)
                if attempted is not None:
                    asset = attempted
                    break
        finally:
            if self._client is None:
                await client.aclose()

        if asset is not None:
            status = FullTextAcquisitionStatus.AVAILABLE
            error = None
        elif not locations:
            status = (
                FullTextAcquisitionStatus.ABSTRACT_ONLY
                if work.abstract
                else FullTextAcquisitionStatus.UNAVAILABLE
            )
            error = "No open-access full-text location is recorded for this work"
        else:
            status = FullTextAcquisitionStatus.RETRIEVAL_FAILED
            error = str(attempts[-1].get("detail")) if attempts else "Retrieval failed"

        row.status = status
        row.error = error
        row.last_attempt_at = datetime.now(UTC)
        row.attempts = [*row.attempts, *attempts]
        return AcquisitionOutcome(
            status=status, asset_id=asset.id if asset else None, attempts=attempts, error=error
        )

    async def _attempt(
        self,
        work: WorkRecord,
        location: OpenAccessLocation,
        licenses: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> tuple[dict[str, Any], FullTextAsset | None]:
        record: dict[str, Any] = {
            "source_type": FullTextSourceType.OPEN_ACCESS.value,
            "provider": location.provider,
            "url": location.url,
            "at": datetime.now(UTC).isoformat(),
        }
        try:
            content = await fetch(location.url, client, check_dns=self._client is None)
            asset, created = await self._store_asset(
                work,
                content,
                source_type=FullTextSourceType.OPEN_ACCESS,
                source_url=location.url,
                uploaded_by=None,
                license_data={
                    **licenses,
                    "location_license": location.license,
                    "location_version": location.version,
                },
            )
        except FullTextRejected as exc:
            return {**record, "outcome": "REJECTED", "detail": str(exc)}, None
        except (httpx.HTTPError, OSError) as exc:
            return {**record, "outcome": "ERROR", "detail": f"{type(exc).__name__}: {exc}"}, None
        return {
            **record,
            "outcome": "STORED" if created else "DEDUPLICATED",
            "sha256": asset.sha256,
        }, asset
