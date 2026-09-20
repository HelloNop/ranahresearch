"""Persists a parse: asset bytes in, ParsedDocument and DocumentChunks out.

A failed parse never destroys the asset. The asset is marked FAILED and kept,
so the same bytes can be re-parsed later by a better parser.
"""

import uuid

from ranah_domain.enums import FullTextAssetStatus
from ranah_domain.models.fulltext import DocumentChunk, FullTextAsset, ParsedDocument
from ranah_domain.storage import ObjectStorage
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_documents.chunking import MAX_CHUNK_TOKENS, OVERLAP_TOKENS, chunk_document
from ranah_documents.parsing import DocumentParseError, DocumentParser, PdfParser


class DocumentParsingService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        parser: DocumentParser | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._parser: DocumentParser = parser or PdfParser()

    async def parse_asset(self, asset: FullTextAsset) -> ParsedDocument:
        asset.status = FullTextAssetStatus.PARSING
        await self._session.flush()
        content = await self._storage.get(asset.storage_key)
        try:
            result = await self._parser.parse(content)
        except DocumentParseError as exc:
            asset.status = FullTextAssetStatus.FAILED
            raise exc

        document = ParsedDocument(
            full_text_asset_id=asset.id,
            parser_name=result.parser_name,
            parser_version=result.parser_version,
            page_count=result.page_count,
            structure={
                "sections": [
                    {
                        "section_type": section.section_type,
                        "heading_text": section.heading_text,
                        "path": section.path,
                        "char_start": section.char_start,
                        "char_end": section.char_end,
                    }
                    for section in result.sections
                ],
                "pages": [
                    {
                        "number": page.number,
                        "char_start": page.char_start,
                        "char_end": page.char_end,
                    }
                    for page in result.pages
                ],
                "chunking": {"max_tokens": MAX_CHUNK_TOKENS, "overlap_tokens": OVERLAP_TOKENS},
            },
            warnings=result.warnings,
            status=result.status,
        )
        self._session.add(document)
        await self._session.flush()

        for chunk in chunk_document(result):
            self._session.add(
                DocumentChunk(
                    parsed_document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_path=chunk.section_path[:500],
                    section_type=chunk.section_type,
                    heading_text=chunk.heading_text,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                )
            )
        asset.status = FullTextAssetStatus.PARSED
        await self._session.flush()
        return document


async def parse_work_asset(
    session: AsyncSession,
    storage: ObjectStorage,
    asset_id: uuid.UUID,
    parser: DocumentParser | None = None,
) -> ParsedDocument:
    asset = await session.get(FullTextAsset, asset_id)
    if asset is None:
        raise DocumentParseError("The asset no longer exists")
    return await DocumentParsingService(session, storage, parser).parse_asset(asset)
