import asyncio
import io
import json
import zipfile

import httpx
import pytest

from app.services.ingestion import (
    AttachmentIngestionService,
    AttachmentTooLargeError,
    UnsafeUrlError,
    UnsupportedAttachmentError,
)


def _docx_bytes(text: str) -> bytes:
    output = io.BytesIO()
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "needle"),
    [
        ("brief.txt", "text/plain", "产品卖点：轻便".encode(), "轻便"),
        ("notes.md", "text/markdown", b"# Hook\nFast opening", "Fast opening"),
        ("rows.csv", "text/csv", b"name,value\nwallet,thin", "wallet\tthin"),
        ("data.json", "application/json", json.dumps({"hook": "problem"}).encode(), '"hook": "problem"'),
        ("page.html", "text/html", b"<h1>Title</h1><script>secret()</script><p>Body</p>", "Title\nBody"),
        ("simple.pdf", "application/pdf", b"%PDF-1.4\nBT (Hello PDF) Tj ET\n%%EOF", "Hello PDF"),
        ("brief.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", _docx_bytes("Hello DOCX"), "Hello DOCX"),
    ],
)
def test_basic_document_parsing(filename, content_type, content, needle):
    async def run():
        service = AttachmentIngestionService()
        result = await service.ingest_bytes(filename, content, content_type)
        assert needle in result.parsed_text
        assert result.metadata["parse_status"] == "parsed"

    asyncio.run(run())


def test_media_is_accepted_without_fake_text():
    async def run():
        service = AttachmentIngestionService()
        result = await service.ingest_bytes("reference.mov", b"media-bytes", "video/quicktime")
        assert result.media_kind == "video"
        assert result.parsed_text == ""
        assert result.metadata["parse_status"] == "no_text"

    asyncio.run(run())


def test_unknown_attachment_is_rejected():
    async def run():
        service = AttachmentIngestionService()
        with pytest.raises(UnsupportedAttachmentError):
            await service.ingest_bytes("payload.exe", b"MZ", "application/octet-stream")

    asyncio.run(run())


def test_stream_limit_is_enforced():
    async def run():
        async def chunks():
            yield b"1234"
            yield b"5678"

        service = AttachmentIngestionService(max_bytes=7)
        with pytest.raises(AttachmentTooLargeError):
            await service.ingest_stream("large.txt", chunks(), "text/plain")

    asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/secret",
        "http://127.0.0.1/secret",
        "http://169.254.169.254/latest/meta-data",
        "http://user:password@example.com/file.txt",
        "https://example.com:8443/file.txt",
    ],
)
def test_ssrf_unsafe_urls_are_rejected(url):
    async def run():
        service = AttachmentIngestionService(resolver=lambda host, port: ["93.184.216.34"])
        with pytest.raises(UnsafeUrlError):
            await service.validate_public_url(url)

    asyncio.run(run())


def test_url_ingestion_parses_public_html():
    async def run():
        async def handler(request):
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=b"<main><h1>Hook</h1><p>Proof</p></main>")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = AttachmentIngestionService(client=client, resolver=lambda host, port: ["93.184.216.34"])
            result = await service.ingest_url("https://example.com/ad.html#fragment")
        assert result.source_url == "https://example.com/ad.html"
        assert result.parsed_text == "Hook\nProof"
        assert result.metadata["redirects"] == 0

    asyncio.run(run())


def test_redirect_to_private_network_is_blocked():
    async def run():
        calls = 0

        async def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private.txt"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = AttachmentIngestionService(client=client, resolver=lambda host, port: ["93.184.216.34"])
            with pytest.raises(UnsafeUrlError):
                await service.ingest_url("https://example.com/start.txt")
        assert calls == 1

    asyncio.run(run())
