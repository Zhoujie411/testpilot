import csv
import io
import json
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader


TEXT_SUFFIXES = {".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".html", ".log"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".csv", ".pdf", ".docx", ".xlsx"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"暂不支持 {suffix or '未知'} 格式")
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".csv":
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        return "\n".join(" | ".join(row) for row in csv.reader(io.StringIO(content)))
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        document = Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    workbook = load_workbook(path, read_only=True, data_only=True)
    lines = []
    for sheet in workbook.worksheets:
        lines.append(f"## 工作表：{sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            lines.append(" | ".join("" if value is None else str(value) for value in row))
    return "\n".join(lines)


def compact_attachment_context(items: list[dict], max_chars: int = 60_000) -> str:
    chunks = []
    used = 0
    for item in items:
        header = f"\n\n===== 附件：{item['original_name']} =====\n"
        remaining = max_chars - used - len(header)
        if remaining <= 0:
            break
        text = item["content_text"][:remaining]
        chunks.append(header + text)
        used += len(header) + len(text)
    return "".join(chunks)
