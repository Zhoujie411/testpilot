"""安全的网页抓取与正文提取，供 AI Agent 读取需求链接使用。

抓取策略：
1. 静态抓取（httpx）：快、轻量，适合正文在 HTML 中静态输出的页面
2. 无头浏览器渲染（Playwright Chromium）：处理 JavaScript 动态渲染的 SPA 页面
   （墨刀、Axure 在线分享等）。服务器未安装 Playwright 时自动降级为纯静态抓取。

安全约束（两条路径都生效）：
- 仅允许 http/https
- 解析域名后拒绝内网、回环、链路本地、保留与组播地址（防 SSRF）
- 浏览器渲染时，页面内发出的每一个子请求（XHR、重定向、iframe）都重新校验目标主机
- 响应体大小限制 5MB，渲染超时 20 秒，同一时刻只允许一个渲染任务
"""

import ipaddress
import re
import socket
import tempfile
import threading
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx

from app.attachment_parser import SUPPORTED_SUFFIXES, TEXT_SUFFIXES, extract_text

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    RENDER_AVAILABLE = True
except ImportError:
    RENDER_AVAILABLE = False

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
MAX_CONTENT_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (compatible; TestPilotAgent/0.1)"
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_RENDER_TEXT = 100_000
_RENDER_LOCK = threading.Lock()


class LinkRejected(ValueError):
    """链接本身不合法或指向内网（不可通过渲染重试）。"""


def read_url_text(url: str) -> tuple[str, str, int]:
    """读取链接正文：先静态抓取，失败或正文为空时回退到无头浏览器渲染。"""
    static_error: ValueError | None = None
    try:
        text, final_url, size = fetch_url_text(url)
        if text.strip():
            return text, final_url, size
        static_error = ValueError("页面正文为空")
    except LinkRejected:
        raise
    except ValueError as error:
        static_error = error
    if not RENDER_AVAILABLE:
        raise ValueError(
            f"{static_error}；且服务器未安装 Playwright 渲染引擎，无法读取 JavaScript 动态渲染的页面"
            "（安装：pip install playwright && playwright install chromium）"
        )
    return render_url_text(url)


def render_url_text(url: str) -> tuple[str, str, int]:
    """用无头浏览器渲染页面并提取正文，返回 (文本, 最终 URL, 文本字节数)。"""
    _parse_and_validate(url)
    if not _RENDER_LOCK.acquire(timeout=45):
        raise ValueError("渲染引擎繁忙，请稍后重试")
    try:
        return _render(url)
    finally:
        _RENDER_LOCK.release()


def _render(url: str) -> tuple[str, str, int]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            # --no-sandbox：systemd NoNewPrivileges 环境下 Chromium 沙箱不可用；
            # 风险由 _route_guard 对全部请求的主机校验兜底
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
            )
            context.route("**/*", _route_guard)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            except PlaywrightTimeout:
                pass  # 超时也尝试提取已渲染的内容
            except PlaywrightError as error:
                raise ValueError(f"页面渲染失败：{error}") from error
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except PlaywrightError:
                pass  # 等不到完全空闲就继续提取
            parts = []
            for frame in page.frames:
                try:
                    frame_text = frame.evaluate("document.body ? document.body.innerText : ''")
                except PlaywrightError:
                    continue
                if frame_text and frame_text.strip():
                    parts.append(frame_text.strip())
            text = "\n\n".join(parts)[:MAX_RENDER_TEXT]
            return text, page.url, len(text.encode("utf-8"))
        finally:
            browser.close()


def _route_guard(route) -> None:
    """浏览器内所有请求的守门人：私网地址直接中断，图片/音视频/字体跳过以加速渲染。"""
    request = route.request
    host = urlparse(request.url).hostname or ""
    try:
        _validate_hostname(host)
    except ValueError:
        route.abort()
        return
    if request.resource_type in {"image", "media", "font"}:
        route.abort()
        return
    route.continue_()

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
        raise LinkRejected("仅支持 http/https 链接")
    hostname = parsed.hostname
    if not hostname:
        raise LinkRejected("链接缺少主机名")
    _validate_hostname(hostname)


def _validate_hostname(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as error:
        raise LinkRejected(f"无法解析域名：{hostname}") from error
    for info in infos:
        raw = info[4][0]
        try:
            address = ipaddress.ip_address(raw.split("%")[0])
        except ValueError as error:
            raise LinkRejected(f"目标地址无效：{raw}") from error
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
            raise LinkRejected("禁止访问内网、回环或保留地址")


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
