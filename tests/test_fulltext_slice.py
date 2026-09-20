import uuid
from typing import Any, cast

import httpx
import pytest
import ranah_worker_orchestration.fulltext_activities as fulltext
from pdf_fixtures import ACADEMIC_PAPER, build_pdf
from ranah_documents.fulltext import (
    MAX_ASSET_BYTES,
    FullTextRejected,
    content_hash,
    fetch,
    storage_key,
    validate_pdf,
)
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.models.events import ProjectEvent
from ranah_domain.models.fulltext import FullTextAsset
from ranah_domain.models.search import SearchQuery, SearchResult, SearchRun, SearchStrategy
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord
from ranah_domain.storage import object_storage
from ranah_literature.models import ProviderWork
from ranah_literature.open_access import license_metadata, public_url, resolve_locations
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration.fulltext_workflows import FullTextAcquisitionWorkflow
from ranah_workflow import connect_client
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.worker import Worker
from test_research_slice import api_client as api_client

PDF = build_pdf(ACADEMIC_PAPER)
OA_URL = "https://repository.example.test/paper.pdf"


def openalex_record(*, oa: bool) -> ProviderWork:
    location = {
        "is_oa": oa,
        "pdf_url": OA_URL if oa else None,
        "license": "cc-by",
        "version": "publishedVersion",
    }
    return ProviderWork(
        provider="openalex",
        provider_id="W1",
        title="Generative AI and university learning outcomes",
        raw_metadata={
            "open_access": {"is_oa": oa, "oa_status": "gold" if oa else "closed"},
            "best_oa_location": location if oa else None,
            "locations": [location] if oa else [],
        },
    )


def test_resolves_only_open_access_locations() -> None:
    crossref = ProviderWork(
        provider="crossref",
        provider_id="10.1234/ai",
        title="Paper",
        raw_metadata={
            "license": [{"URL": "http://creativecommons.org/licenses/by/4.0/"}],
            "link": [
                {
                    "URL": "https://publisher.example.test/tdm.pdf",
                    "content-type": "application/pdf",
                }
            ],
        },
    )
    semantic = ProviderWork(
        provider="semantic_scholar",
        provider_id="S1",
        title="Paper",
        raw_metadata={
            "isOpenAccess": True,
            "openAccessPdf": {"url": "https://s2.example.test/paper.pdf", "status": "GOLD"},
        },
    )
    records = [openalex_record(oa=True), crossref, semantic]
    locations = resolve_locations(records)

    urls = [location.url for location in locations]
    # A Crossref text-mining link is never a download target, even with an open license.
    assert "https://publisher.example.test/tdm.pdf" not in urls
    assert urls == [OA_URL, "https://s2.example.test/paper.pdf"]
    assert locations[0].license == "cc-by"
    assert license_metadata(records)["crossref_license"][0]["URL"].startswith("http")

    assert resolve_locations([openalex_record(oa=False), crossref]) == []


def test_rejects_non_open_access_url_schemes() -> None:
    record = ProviderWork(
        provider="openalex",
        provider_id="W2",
        title="Paper",
        raw_metadata={
            "best_oa_location": {"is_oa": True, "pdf_url": "file:///etc/passwd"},
            "locations": [{"is_oa": True, "pdf_url": "ftp://example.test/p.pdf"}],
        },
    )
    assert resolve_locations([record]) == []


def test_rejects_private_open_access_locations() -> None:
    assert public_url(OA_URL)
    for url in (
        "http://127.0.0.1/paper.pdf",
        "http://[::1]/paper.pdf",
        "http://metadata.google.internal/paper.pdf",
        "http://user:password@repository.example.test/paper.pdf",
        "http://[invalid/paper.pdf",
    ):
        assert not public_url(url)


async def test_remote_fetch_does_not_follow_redirects() -> None:
    requests: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/paper.pdf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch(OA_URL, client, check_dns=False)
    assert len(requests) == 1


def test_content_validation() -> None:
    validate_pdf(PDF)
    with pytest.raises(FullTextRejected, match="empty"):
        validate_pdf(b"")
    with pytest.raises(FullTextRejected, match="not a PDF"):
        validate_pdf(b"<html><body>Purchase this article</body></html>")
    with pytest.raises(FullTextRejected, match="limit"):
        validate_pdf(b"%PDF-" + b"0" * MAX_ASSET_BYTES)


def test_storage_key_is_content_addressed() -> None:
    project_id, work_id = uuid.uuid4(), uuid.uuid4()
    digest = content_hash(PDF)
    key = storage_key(project_id, work_id, digest)
    assert key == f"projects/{project_id}/works/{work_id}/full-text/{digest}.pdf"
    assert content_hash(PDF) == content_hash(PDF) != content_hash(PDF + b" ")


async def seed_work(
    engine: AsyncEngine,
    project_id: uuid.UUID,
    *,
    abstract: str | None = "An abstract",
    records: list[ProviderWork] | None = None,
) -> uuid.UUID:
    """A canonical work, optionally with the provider payloads discovery stored."""
    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        work = WorkRecord(
            project_id=project_id, title="Generative AI and learning", abstract=abstract
        )
        session.add(work)
        await session.flush()
        if records:
            strategy = SearchStrategy(project_id=project_id)
            session.add(strategy)
            await session.flush()
            query = SearchQuery(
                search_strategy_id=strategy.id, provider="openalex", query_text="ai"
            )
            session.add(query)
            await session.flush()
            run = SearchRun(
                project_id=project_id,
                search_query_id=query.id,
                provider="openalex",
                executed_query="ai",
            )
            session.add(run)
            await session.flush()
            for record in records:
                session.add(
                    SearchResult(
                        search_run_id=run.id,
                        provider_record_id=record.provider_id,
                        normalized_payload=record.model_dump(mode="json"),
                    )
                )
                session.add(
                    WorkMetadataObservation(
                        work_id=work.id,
                        provider=record.provider,
                        field_name="provider_record_id",
                        field_value={"value": record.provider_id},
                    )
                )
        return work.id


async def test_upload_stores_hashes_and_deduplicates(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    project_id = (await api_client.post("/projects", json={"idea": "AI"})).json()["id"]
    work_id = await seed_work(db_engine, uuid.UUID(project_id))
    base = f"/projects/{project_id}/works/{work_id}/full-text"

    assert (await api_client.get(base)).json()["status"] == "NOT_REQUESTED"

    response = await api_client.post(
        base + "/upload", files={"file": ("paper.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "AVAILABLE" and body["stored_new_file"] is True
    asset = body["assets"][0]
    assert asset["sha256"] == content_hash(PDF)
    assert asset["source_type"] == "USER_UPLOAD" and asset["byte_size"] == len(PDF)
    assert await object_storage().get(asset["storage_key"]) == PDF

    repeat = await api_client.post(
        base + "/upload", files={"file": ("same-paper-renamed.pdf", PDF, "application/pdf")}
    )
    assert repeat.status_code == 201
    assert repeat.json()["stored_new_file"] is False
    assert len(repeat.json()["assets"]) == 1

    factory = create_session_factory(db_engine)
    async with session_scope(factory) as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(FullTextAsset)
                .where(FullTextAsset.work_id == work_id)
            )
        ) == 1
        uploads = await session.scalars(
            select(ProjectEvent).where(
                ProjectEvent.project_id == uuid.UUID(project_id),
                ProjectEvent.event_type == "FULL_TEXT_UPLOADED",
            )
        )
        # Both uploads stay auditable even though only one blob exists.
        assert len(list(uploads)) == 2


async def test_upload_rejects_invalid_content(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    project_id = (await api_client.post("/projects", json={"idea": "AI"})).json()["id"]
    work_id = await seed_work(db_engine, uuid.UUID(project_id))
    base = f"/projects/{project_id}/works/{work_id}/full-text"

    html = await api_client.post(
        base + "/upload", files={"file": ("paper.pdf", b"<html>paywall</html>", "application/pdf")}
    )
    assert html.status_code == 422 and "not a PDF" in html.text

    assert (await api_client.post(base + "/upload")).status_code == 422
    assert (
        await api_client.post(
            base + "/upload", files={"file": ("empty.pdf", b"", "application/pdf")}
        )
    ).status_code == 422

    missing = f"/projects/{project_id}/works/{uuid.uuid4()}/full-text/upload"
    assert (
        await api_client.post(missing, files={"file": ("p.pdf", PDF, "application/pdf")})
    ).status_code == 404

    async with session_scope(create_session_factory(db_engine)) as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(FullTextAsset)
                .where(FullTextAsset.work_id == work_id)
            )
        ) == 0


async def test_upload_requires_project_access(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    project_id = (await api_client.post("/projects", json={"idea": "AI"})).json()["id"]
    work_id = await seed_work(db_engine, uuid.UUID(project_id))
    other = f"/projects/{uuid.uuid4()}/works/{work_id}/full-text/upload"
    assert (
        await api_client.post(other, files={"file": ("p.pdf", PDF, "application/pdf")})
    ).status_code == 404


def pdf_transport(status: int = 200, body: bytes = PDF) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("open_access", "AVAILABLE"),
        ("paywall_html", "RETRIEVAL_FAILED"),
        ("http_error", "RETRIEVAL_FAILED"),
        ("no_location_with_abstract", "ABSTRACT_ONLY"),
        ("no_location_without_abstract", "UNAVAILABLE"),
    ],
)
async def test_acquisition_outcomes(
    api_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: str,
) -> None:
    has_location = mode in ("open_access", "paywall_html", "http_error")
    project_id = (await api_client.post("/projects", json={"idea": "AI"})).json()["id"]
    work_id = await seed_work(
        db_engine,
        uuid.UUID(project_id),
        abstract=None if mode == "no_location_without_abstract" else "An abstract",
        records=[openalex_record(oa=has_location)],
    )
    client = {
        "open_access": pdf_transport(),
        "paywall_html": pdf_transport(body=b"<html>Buy this article</html>"),
        "http_error": pdf_transport(status=503),
    }.get(mode, pdf_transport())
    monkeypatch.setattr(fulltext, "http_client", lambda: client)

    queue_name = f"fulltext-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue_name)
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue_name,
        workflows=[FullTextAcquisitionWorkflow],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            fulltext.prepare_acquisition_batch,
            fulltext.acquire_full_text_batch,
            fulltext.calculate_acquisition_progress,
        ],
    ):
        base = f"/projects/{project_id}/works/{work_id}/full-text"
        response = await api_client.post(base + "/acquire")
        assert response.status_code == 202, response.text
        operation_id = response.json()["operation_id"]
        assert (
            await temporal.get_workflow_handle(f"research-{operation_id}").result() == "COMPLETED"
        )

        view = cast(dict[str, Any], (await api_client.get(base)).json())
        assert view["status"] == expected, view
        if expected == "AVAILABLE":
            asset = view["assets"][0]
            assert asset["source_type"] == "OPEN_ACCESS" and asset["source_url"] == OA_URL
            assert asset["license_metadata"]["location_license"] == "cc-by"
            assert await object_storage().get(asset["storage_key"]) == PDF
        else:
            assert view["assets"] == []
            assert view["error"]
        if has_location:
            assert view["attempts"][0]["url"] == OA_URL
        else:
            # Nothing was fetched, and that is recorded as a retrieval fact.
            assert view["attempts"] == []

    await client.aclose()


async def test_project_acquisition_is_resumable(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed work does not block the run, and rerunning does not duplicate assets."""
    project_id = (await api_client.post("/projects", json={"idea": "AI"})).json()["id"]
    good = await seed_work(db_engine, uuid.UUID(project_id), records=[openalex_record(oa=True)])
    bad = await seed_work(db_engine, uuid.UUID(project_id), records=[openalex_record(oa=True)])

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, content=PDF if calls["count"] % 2 else b"not-a-pdf")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(fulltext, "http_client", lambda: client)
    monkeypatch.setenv("FULL_TEXT_BATCH_SIZE", "1")
    queue_name = f"fulltext-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue_name)
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue_name,
        workflows=[FullTextAcquisitionWorkflow],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            fulltext.prepare_acquisition_batch,
            fulltext.acquire_full_text_batch,
            fulltext.calculate_acquisition_progress,
        ],
    ):
        base = f"/projects/{project_id}"
        for work_id in (good, bad):
            response = await api_client.post(f"{base}/works/{work_id}/full-text/acquire")
            operation_id = response.json()["operation_id"]
            await temporal.get_workflow_handle(f"research-{operation_id}").result()

        statuses = {
            item["work_id"]: item["status"]
            for item in (await api_client.get(base + "/full-text/status")).json()["items"]
        }
        assert statuses[str(good)] == "AVAILABLE"
        assert statuses[str(bad)] == "RETRIEVAL_FAILED"

        # Re-acquiring an already-available work stores no second asset.
        response = await api_client.post(f"{base}/works/{good}/full-text/acquire")
        await temporal.get_workflow_handle(f"research-{response.json()['operation_id']}").result()

    async with session_scope(create_session_factory(db_engine)) as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(FullTextAsset)
                .where(FullTextAsset.project_id == uuid.UUID(project_id))
            )
        ) == 1
    overview = (await api_client.get(f"/projects/{project_id}/full-text/status")).json()
    assert overview["total"] == 2 and overview["counts"]["AVAILABLE"] == 1
    await client.aclose()
