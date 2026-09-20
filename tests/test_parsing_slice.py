import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx
import pytest
import ranah_worker_orchestration.parsing_activities as parsing
from pdf_fixtures import ACADEMIC_PAPER, build_pdf
from ranah_documents.chunking import MAX_CHUNK_TOKENS, chunk_document, count_tokens
from ranah_documents.parsing import (
    DocumentParseError,
    PdfParser,
    detect_sections,
    strip_running_lines,
)
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.models.fulltext import DocumentChunk, FullTextAsset, ParsedDocument
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration.parsing_workflows import FullTextParsingWorkflow
from ranah_workflow import connect_client
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.worker import Worker
from test_fulltext_slice import seed_work
from test_research_slice import api_client as api_client

PDF = build_pdf(ACADEMIC_PAPER)


async def test_parser_preserves_pages_and_sections() -> None:
    result = await PdfParser().parse(PDF)

    assert result.parser_name == "pypdf" and result.page_count == 3
    assert result.status == "PARSED"
    assert "214 undergraduate students" in result.text

    types = {section.section_type for section in result.sections}
    assert {"ABSTRACT", "INTRODUCTION", "METHODS", "RESULTS", "DISCUSSION", "REFERENCES"} <= types

    methods = next(s for s in result.sections if s.heading_text == "Participants")
    # A heading that is not a canonical section keeps its own text and nests.
    assert methods.section_type == "METHODS" and methods.path == "Methods > Participants"
    assert "214 undergraduate students" in result.text[methods.char_start : methods.char_end]

    # Page provenance is real: the sample size is printed on page 2.
    offset = result.text.index("214 undergraduate students")
    page = next(p for p in result.pages if p.char_start <= offset <= p.char_end)
    assert page.number == 2


async def test_chunks_carry_page_and_section_provenance() -> None:
    result = await PdfParser().parse(PDF)
    chunks = chunk_document(result)

    assert chunks and [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.token_count <= MAX_CHUNK_TOKENS for c in chunks)
    assert all(c.page_start >= 1 and c.page_end >= c.page_start for c in chunks)

    sample = next(c for c in chunks if "214 undergraduate students" in c.text)
    assert sample.page_start == 2
    assert sample.section_type == "METHODS"
    assert "Participants" in sample.section_path
    assert result.text[sample.char_start : sample.char_end] == sample.text

    results_chunk = next(c for c in chunks if "78.4" in c.text)
    assert results_chunk.section_type == "RESULTS" and results_chunk.page_start == 3


def test_running_headers_and_page_numbers_are_removed() -> None:
    pages = [
        "Journal of Learning\nIntroduction\nBody text one\n1",
        "Journal of Learning\nMethods\nBody text two\n2",
        "Journal of Learning\nResults\nBody text three\n3",
    ]
    cleaned, removed = strip_running_lines(pages)
    assert removed == ["Journal of Learning"]
    assert all("Journal of Learning" not in page for page in cleaned)
    assert cleaned[0].splitlines() == ["Introduction", "Body text one"]


def test_sections_without_imrad_headings() -> None:
    sections, warnings = detect_sections("Just a paragraph of prose with no headings at all.")
    assert [s.section_type for s in sections] == ["OTHER"]
    assert any("No section headings" in warning for warning in warnings)

    sections, warnings = detect_sections("Tinjauan Pustaka\nIsi bagian ini.\nPenutup\nRingkasan.")
    # Unknown heading names are preserved rather than forced into IMRaD.
    assert [s.heading_text for s in sections] == ["Tinjauan Pustaka", "Penutup"]
    assert any("uncertain" in warning for warning in warnings)


async def test_unicode_text_survives_extraction() -> None:
    pdf = build_pdf(
        [["Résumé", "Les étudiants (n=214) ont participé à l'étude.", "Präzision: 78,4"]]
    )
    result = await PdfParser().parse(pdf)
    assert "étudiants" in result.text and "Präzision" in result.text


async def test_malformed_pdf_fails_without_destroying_the_asset(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(DocumentParseError):
        await PdfParser().parse(b"%PDF-1.4\nnot really a pdf at all")

    project_id = (await api_client.post("/projects", json={"idea": "AI"})).json()["id"]
    work_id = await seed_work(db_engine, uuid.UUID(project_id))
    base = f"/projects/{project_id}/works/{work_id}/full-text"
    broken = b"%PDF-1.4\n" + b"garbage bytes that no parser can read\n" * 5
    assert (
        await api_client.post(
            base + "/upload", files={"file": ("p.pdf", broken, "application/pdf")}
        )
    ).status_code == 201

    async with parsing_worker(monkeypatch) as temporal:
        response = await api_client.post(base + "/parse")
        assert response.status_code == 202
        operation = response.json()["operation_id"]
        assert await temporal.get_workflow_handle(f"research-{operation}").result() == "COMPLETED"

    view = (await api_client.get(base)).json()
    assert view["assets"][0]["status"] == "FAILED"
    assert view["parsed_document"] is None
    async with session_scope(create_session_factory(db_engine)) as session:
        # The bytes are still on file, so a better parser can retry later.
        asset = await session.scalar(select(FullTextAsset).where(FullTextAsset.work_id == work_id))
        assert asset is not None and asset.storage_key


@asynccontextmanager
async def parsing_worker(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client]:
    queue = f"parsing-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue)
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue,
        workflows=[FullTextParsingWorkflow],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            parsing.prepare_parsing_batch,
            parsing.parse_assets,
            parsing.calculate_parsing_progress,
        ],
    ):
        yield temporal


async def test_parsing_persists_provenance_and_is_idempotent(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = (await api_client.post("/projects", json={"idea": "AI"})).json()["id"]
    work_id = await seed_work(db_engine, uuid.UUID(project_id))
    base = f"/projects/{project_id}/works/{work_id}/full-text"
    assert (await api_client.post(base + "/parse")).status_code == 409

    await api_client.post(base + "/upload", files={"file": ("p.pdf", PDF, "application/pdf")})

    async with parsing_worker(monkeypatch) as temporal:
        response = await api_client.post(base + "/parse")
        operation = response.json()["operation_id"]
        assert await temporal.get_workflow_handle(f"research-{operation}").result() == "COMPLETED"

        view = cast(dict[str, Any], (await api_client.get(base)).json())
        assert view["assets"][0]["status"] == "PARSED"
        document = view["parsed_document"]
        assert document["parser_name"] == "pypdf" and document["page_count"] == 3

        chunks = cast(dict[str, Any], (await api_client.get(base + "/chunks")).json())["chunks"]
        methods = next(c for c in chunks if "214 undergraduate students" in c["text"])
        assert methods["page_start"] == 2 and methods["section_type"] == "METHODS"

        # Re-running parses nothing new rather than duplicating the document.
        repeat = await api_client.post(base + "/parse")
        await temporal.get_workflow_handle(f"research-{repeat.json()['operation_id']}").result()

    async with session_scope(create_session_factory(db_engine)) as session:
        asset = await session.scalar(select(FullTextAsset).where(FullTextAsset.work_id == work_id))
        assert asset is not None
        documents = list(
            await session.scalars(
                select(ParsedDocument).where(ParsedDocument.full_text_asset_id == asset.id)
            )
        )
        assert len(documents) == 1
        stored = list(
            await session.scalars(
                select(DocumentChunk).where(DocumentChunk.parsed_document_id == documents[0].id)
            )
        )
        assert stored and all(chunk.token_count <= MAX_CHUNK_TOKENS for chunk in stored)
        assert count_tokens(stored[0].text) == stored[0].token_count


async def test_parse_results_are_immutable(db_engine: AsyncEngine) -> None:
    async with session_scope(create_session_factory(db_engine)) as session:
        document = await session.scalar(select(ParsedDocument).limit(1))
        if document is None:
            pytest.skip("No parsed document available in this run")
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                text("UPDATE parsed_documents SET page_count = 999 WHERE id = :id"),
                {"id": document.id},
            )
