"""安全的网页抓取与正文提取，供 AI Agent 读取需求链接使用。

安全约束：
- 仅允许 http/https
- 解析域名后拒绝内网、回环、链路本地、保留与组播地址（防 SSRF）
- 手动处理重定向，每一跳都重新校验目标主机
- 响应体大小限制 5MB，防止恶意大页面拖垮服务
"""

import ipaddress
import re
import socket
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx

from app.attachment_parser import SUPPORTED_SUFFIXES, TEXT_SUFFIXES, extract_text

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
MAX_CONTENT_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (compatible; TestPilotAgent/0.1)"
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
_BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "tr", "table", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "blockquote", "pre", "td", "th", "dd", "dt", "dl",
}


def fetch_url_text(url: str) -> tuple[str, str, int]:
    """抓取需求链接并提取纯文本。

    返回 (提取的文本, 最终 URL, 原始响应字节数)。
    链接非法、指向内网或页面异常时抛出 ValueError（中文信息可直接返回给用户）。
    """
    body, final_url, content_type = _fetch(url)
    text = _extract(body, content_type, final_url)
    return text, final_url, len(body)


def _parse_and_validate(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("仅支持 http/https 链接")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("链接缺少主机名")
    _validate_hostname(hostname)


def _validate_hostname(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as error:
        raise ValueError(f"无法解析域名：{hostname}") from error
    for info in infos:
        raw = info[4][0]
        try:
            address = ipaddress.ip_address(raw.split("%")[0])
        except ValueError as error:
            raise ValueError(f"目标地址无效：{raw}") from error
        if address.version == 6:
            mapped = address.ipv4_mapped
            if mapped is not None:
                address = mapped
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValueError("禁止访问内网、回环或保留地址")


def _fetch(url: str) -> tuple[bytes, str, str]:
    current = url.strip()
    with httpx.Client(
        follow_redirects=False,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,application/*;q=0.8,*/*;q=0.5"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _parse_and_validate(current)
            with client.stream("GET", current) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location", "")
                    if not location:
                        raise ValueError(f"重定向缺少目标地址（HTTP {response.status_code}）")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise ValueError(f"目标页面返回 HTTP {response.status_code}")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    total += len(chunk)
                    if total > MAX_CONTENT_BYTES:
                        raise ValueError("页面内容超过 5MB 限制")
                    chunks.append(chunk)
                return b"".join(chunks), current, response.headers.get("content-type", "")
    raise ValueError("重定向次数超过限制（可能存在循环）")


def _extract(body: bytes, content_type: str, url: str) -> str:
    kind, suffix = _classify(content_type, url)
    if kind == "html":
        return _html_to_text(_decode_text(body, content_type))
    if kind == "file":
        temp_path = Path(tempfile.gettempdir()) / f"testpilot-fetch-{uuid4().hex}{suffix}"
        temp_path.write_bytes(body)
        try:
            return extract_text(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
    return _decode_text(body, content_type).strip()


def _classify(content_type: str, url: str) -> tuple[str, str]:
    """按 URL 后缀与 Content-Type 判定处理方式，返回 ("html" | "file" | "text", 后缀)。"""
    ctype = content_type.split(";")[0].strip().lower()
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".pdf", ".docx", ".xlsx", ".csv"}:
        return "file", suffix
    if ctype in HTML_CONTENT_TYPES:
        return "html", ".html"
    if "pdf" in ctype:
        return "file", ".pdf"
    if "wordprocessingml" in ctype:
        return "file", ".docx"
    if "spreadsheetml" in ctype:
        return "file", ".xlsx"
    if suffix in TEXT_SUFFIXES or suffix in SUPPORTED_SUFFIXES:
        return "text", suffix
    if ctype.startswith("text/") or ctype in {"application/json", "application/xml"}:
        return "text", ""
    raise ValueError(
        f"不支持的链接内容类型：{ctype or '未知'}（页面可能需要登录后访问，建议导出文件后上传）"
    )


def _decode_text(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    for candidate in (match.group(1) if match else None, "utf-8", "gb18030"):
        if not candidate:
            continue
        try:
            return body.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    extractor.close()
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(extractor.parts).splitlines())
    return "\n".join(line for line in lines if line)
