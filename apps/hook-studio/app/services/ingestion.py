from __future__ import annotations

import asyncio
import csv
import inspect
import ipaddress
import io
import json
import mimetypes
import re
import socket
import zlib
import zipfile
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, AsyncIterable, Awaitable, BinaryIO, Callable, Iterable
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree

import httpx


class IngestionError(ValueError):
    pass


class UnsafeUrlError(IngestionError):
    pass


class UnsupportedAttachmentError(IngestionError):
    pass


class AttachmentTooLargeError(IngestionError):
    pass


@dataclass(frozen=True)
class IngestedContent:
    filename: str
    content_type: str
    media_kind: str
    size_bytes: int
    content: bytes = field(repr=False)
    parsed_text: str = ""
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".srt", ".vtt"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v", ".mpeg", ".mpg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

MIME_KIND = {
    "text/plain": "text",
    "text/markdown": "text",
    "text/csv": "text",
    "text/html": "text",
    "text/vtt": "text",
    "application/json": "text",
    "application/pdf": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "document",
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/gif": "image",
    "video/mp4": "video",
    "video/quicktime": "video",
    "video/webm": "video",
    "video/mpeg": "video",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/aac": "audio",
    "audio/ogg": "audio",
    "audio/flac": "audio",
}

Resolver = Callable[[str, int], Awaitable[list[str]] | list[str]]


def _safe_filename(filename: str) -> str:
    value = Path(unquote(filename)).name.strip()
    if not value or value in {".", ".."} or "\x00" in value:
        raise UnsupportedAttachmentError("附件文件名无效")
    return value


def _normal_content_type(content_type: str | None, filename: str) -> str:
    provided = (content_type or "").split(";", 1)[0].strip().lower()
    return provided or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _extension_kind(extension: str) -> str | None:
    if extension in TEXT_EXTENSIONS:
        return "text"
    if extension in DOCUMENT_EXTENSIONS:
        return "document"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    return None


def classify_attachment(filename: str, content_type: str | None = None) -> tuple[str, str]:
    safe_name = _safe_filename(filename)
    extension = Path(safe_name).suffix.lower()
    resolved_type = _normal_content_type(content_type, safe_name)
    kind = MIME_KIND.get(resolved_type) or _extension_kind(extension)
    if kind is None or (extension and extension not in ALLOWED_EXTENSIONS):
        raise UnsupportedAttachmentError(f"暂不支持该附件格式: {extension or resolved_type}")
    return kind, resolved_type


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


class _VisibleHTMLParser(HTMLParser):
    BLOCK_TAGS = {"article", "aside", "blockquote", "br", "div", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "p", "section", "table", "tr"}
    HIDDEN_TAGS = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in self.HIDDEN_TAGS:
            self.hidden_depth += 1
        elif not self.hidden_depth and lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self.HIDDEN_TAGS and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


def _parse_html(content: bytes) -> str:
    parser = _VisibleHTMLParser()
    parser.feed(_decode_text(content))
    parser.close()
    return parser.text()


def _parse_csv(content: bytes) -> str:
    text = _decode_text(content)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    rows = csv.reader(io.StringIO(text), dialect)
    return "\n".join("\t".join(cell.strip() for cell in row) for row in rows)


def _parse_json(content: bytes) -> str:
    try:
        value = json.loads(_decode_text(content))
    except json.JSONDecodeError as exc:
        raise IngestionError(f"JSON解析失败: {exc.msg}") from exc
    return json.dumps(value, ensure_ascii=False, indent=2)


def _decode_pdf_bytes(value: bytes) -> str:
    if value.startswith(b"\xfe\xff"):
        return value[2:].decode("utf-16-be", errors="replace")
    for encoding in ("utf-8", "gb18030", "cp1252"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("latin-1", errors="replace")


def _decode_pdf_literal(token: bytes) -> str:
    raw = token[1:-1]
    output = bytearray()
    idx = 0
    escapes = {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b", ord("f"): b"\f"}
    while idx < len(raw):
        byte = raw[idx]
        if byte != 0x5C:
            output.append(byte)
            idx += 1
            continue
        idx += 1
        if idx >= len(raw):
            break
        current = raw[idx]
        if current in escapes:
            output.extend(escapes[current])
            idx += 1
        elif current in b"()\\":
            output.append(current)
            idx += 1
        elif current in b"\r\n":
            if current == 0x0D and idx + 1 < len(raw) and raw[idx + 1] == 0x0A:
                idx += 1
            idx += 1
        elif 0x30 <= current <= 0x37:
            end = idx + 1
            while end < min(idx + 3, len(raw)) and 0x30 <= raw[end] <= 0x37:
                end += 1
            output.append(int(raw[idx:end], 8))
            idx = end
        else:
            output.append(current)
            idx += 1
    return _decode_pdf_bytes(bytes(output))


def _decode_pdf_token(token: bytes) -> str:
    if token.startswith(b"("):
        return _decode_pdf_literal(token)
    compact = re.sub(rb"\s+", b"", token[1:-1])
    if len(compact) % 2:
        compact += b"0"
    try:
        return _decode_pdf_bytes(bytes.fromhex(compact.decode("ascii")))
    except (ValueError, UnicodeDecodeError):
        return ""


def _parse_pdf(content: bytes) -> str:
    sources = [content]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", content, flags=re.DOTALL):
        stream = match.group(1)
        header = content[max(0, match.start() - 512) : match.start()]
        if b"/FlateDecode" in header:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        sources.append(stream)
    token_pattern = rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]+>"
    parts: list[str] = []
    for source in sources:
        for match in re.finditer(rb"(" + token_pattern + rb")\s*Tj", source, flags=re.DOTALL):
            parts.append(_decode_pdf_token(match.group(1)))
        for array in re.finditer(rb"\[(.*?)\]\s*TJ", source, flags=re.DOTALL):
            joined = "".join(_decode_pdf_token(token.group(0)) for token in re.finditer(token_pattern, array.group(1), flags=re.DOTALL))
            if joined:
                parts.append(joined)
    unique: list[str] = []
    for part in parts:
        clean = re.sub(r"\s+", " ", part).strip()
        if clean and clean not in unique:
            unique.append(clean)
    return "\n".join(unique)


def _parse_docx(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > 5000 or sum(item.file_size for item in infos) > 100 * 1024 * 1024:
                raise IngestionError("DOCX解压内容过大")
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise IngestionError("DOCX解析失败") from exc
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise IngestionError("DOCX正文XML解析失败") from exc
    paragraphs: list[str] = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        text = "".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _parse_openxml(content: bytes, kind: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > 10000 or sum(item.file_size for item in infos) > 200 * 1024 * 1024:
                raise IngestionError("Office文档解压内容过大")
            names = archive.namelist()
            if kind == "xlsx":
                targets = sorted(name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
                targets = (["xl/sharedStrings.xml"] if "xl/sharedStrings.xml" in names else []) + targets
            else:
                targets = sorted(name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
            parts: list[str] = []
            for name in targets:
                root = ElementTree.fromstring(archive.read(name))
                text = [node.text.strip() for node in root.iter() if node.text and node.text.strip() and (node.tag.endswith("}t") or node.tag.endswith("}v"))]
                if text:
                    parts.append(f"[{Path(name).stem}]\n" + "\t".join(text))
            return "\n".join(parts)
    except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise IngestionError("Office文档解析失败") from exc


def parse_attachment_text(filename: str, content_type: str, content: bytes, *, max_chars: int = 200_000) -> str:
    extension = Path(filename).suffix.lower()
    if extension in {".html", ".htm"} or content_type == "text/html":
        text = _parse_html(content)
    elif extension == ".csv" or content_type == "text/csv":
        text = _parse_csv(content)
    elif extension == ".json" or content_type == "application/json":
        text = _parse_json(content)
    elif extension == ".pdf" or content_type == "application/pdf":
        text = _parse_pdf(content)
    elif extension == ".docx" or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        text = _parse_docx(content)
    elif extension == ".xlsx" or content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        text = _parse_openxml(content, "xlsx")
    elif extension == ".pptx" or content_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        text = _parse_openxml(content, "pptx")
    else:
        text = _decode_text(content)
    return text[:max_chars]


async def _default_resolver(hostname: str, port: int) -> list[str]:
    infos = await asyncio.to_thread(socket.getaddrinfo, hostname, port, type=socket.SOCK_STREAM)
    return sorted({str(item[4][0]).split("%", 1)[0] for item in infos})


class AttachmentIngestionService:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolver: Resolver | None = None,
        max_bytes: int = 64 * 1024 * 1024,
        max_chars: int = 200_000,
        max_redirects: int = 3,
    ) -> None:
        self._client = client
        self._resolver = resolver or _default_resolver
        self.max_bytes = max_bytes
        self.max_chars = max_chars
        self.max_redirects = max_redirects

    async def validate_public_url(self, url: str) -> str:
        parsed = urlsplit(url.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            raise UnsafeUrlError("链接仅支持HTTP或HTTPS")
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise UnsafeUrlError("链接主机或认证信息无效")
        if "%" in parsed.hostname:
            raise UnsafeUrlError("链接不允许IPv6区域标识")
        try:
            hostname = parsed.hostname.encode("idna").decode("ascii").rstrip(".").lower()
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        except (UnicodeError, ValueError) as exc:
            raise UnsafeUrlError("链接主机或端口无效") from exc
        if port not in {80, 443}:
            raise UnsafeUrlError("链接仅允许80或443端口")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise UnsafeUrlError("链接不能指向本地或内部主机")
        try:
            literal = ipaddress.ip_address(hostname)
            addresses = [str(literal)]
        except ValueError:
            resolved = self._resolver(hostname, port)
            addresses = await resolved if inspect.isawaitable(resolved) else resolved
        if not addresses:
            raise UnsafeUrlError("链接域名无法解析")
        for address in addresses:
            try:
                ip = ipaddress.ip_address(str(address).split("%", 1)[0])
            except ValueError as exc:
                raise UnsafeUrlError("链接解析结果不是有效IP") from exc
            if not ip.is_global:
                raise UnsafeUrlError("链接不能指向内网、回环或保留地址")
        return parsed._replace(netloc=parsed.netloc.lower(), fragment="").geturl()

    async def ingest_bytes(self, filename: str, content: bytes, content_type: str | None = None) -> IngestedContent:
        safe_name = _safe_filename(filename)
        if not content:
            raise IngestionError("附件内容为空")
        if len(content) > self.max_bytes:
            raise AttachmentTooLargeError(f"附件不能超过{self.max_bytes // (1024 * 1024) or 1}MB")
        media_kind, resolved_type = classify_attachment(safe_name, content_type)
        parsed_text = ""
        if media_kind in {"text", "document"}:
            parsed_text = parse_attachment_text(safe_name, resolved_type, content, max_chars=self.max_chars)
        return IngestedContent(
            filename=safe_name,
            content_type=resolved_type,
            media_kind=media_kind,
            size_bytes=len(content),
            content=content,
            parsed_text=parsed_text,
            metadata={"parse_status": "parsed" if parsed_text else "no_text", "text_chars": len(parsed_text)},
        )

    async def ingest_stream(
        self,
        filename: str,
        stream: BinaryIO | Iterable[bytes] | AsyncIterable[bytes],
        content_type: str | None = None,
    ) -> IngestedContent:
        buffer = bytearray()

        def add(chunk: bytes | bytearray | memoryview) -> None:
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise IngestionError("附件流必须返回bytes")
            buffer.extend(chunk)
            if len(buffer) > self.max_bytes:
                raise AttachmentTooLargeError(f"附件不能超过{self.max_bytes // (1024 * 1024) or 1}MB")

        if hasattr(stream, "read"):
            while True:
                chunk = stream.read(1024 * 1024)  # type: ignore[union-attr]
                if inspect.isawaitable(chunk):
                    chunk = await chunk
                if not chunk:
                    break
                add(chunk)
        elif hasattr(stream, "__aiter__"):
            async for chunk in stream:  # type: ignore[union-attr]
                add(chunk)
        else:
            for chunk in stream:  # type: ignore[union-attr]
                add(chunk)
        return await self.ingest_bytes(filename, bytes(buffer), content_type)

    async def ingest_url(self, url: str) -> IngestedContent:
        client = self._client or httpx.AsyncClient(timeout=60.0, follow_redirects=False, trust_env=False)
        owned = self._client is None
        current = url
        try:
            for redirect_count in range(self.max_redirects + 1):
                current = await self.validate_public_url(current)
                async with client.stream("GET", current, headers={"Accept": "*/*", "User-Agent": "HookStudio-Ingestion/1.0"}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count >= self.max_redirects:
                            raise IngestionError("链接重定向次数过多或缺少目标")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    declared = response.headers.get("content-length")
                    if declared:
                        try:
                            if int(declared) > self.max_bytes:
                                raise AttachmentTooLargeError("远程附件超过大小上限")
                        except ValueError:
                            pass
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > self.max_bytes:
                            raise AttachmentTooLargeError("远程附件超过大小上限")
                    filename = Path(unquote(urlsplit(current).path)).name or "download.txt"
                    result = await self.ingest_bytes(filename, bytes(content), response.headers.get("content-type"))
                    return replace(result, source_url=current, metadata={**result.metadata, "source_url": current, "redirects": redirect_count})
            raise IngestionError("链接重定向次数过多")
        except httpx.HTTPError as exc:
            raise IngestionError(f"远程链接读取失败: {type(exc).__name__}") from exc
        finally:
            if owned:
                await client.aclose()
