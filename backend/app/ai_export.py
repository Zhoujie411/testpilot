import json
import zipfile
from io import BytesIO
from uuid import uuid4

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


def export_excel(payload: dict) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "测试用例"
    headers = ["序号", "模块", "用例标题", "优先级", "类型", "前置条件", "测试步骤", "预期结果"]
    sheet.append(headers)
    for index, case in enumerate(payload.get("cases", []), 1):
        steps = case.get("steps", [])
        sheet.append([
            index,
            case.get("module", ""),
            case.get("title", ""),
            case.get("priority", ""),
            case.get("type", ""),
            case.get("preconditions", ""),
            "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)),
            case.get("expected_result", ""),
        ])
    fill = PatternFill("solid", fgColor="1D2A52")
    for cell in sheet[1]:
        cell.fill = fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center")
    widths = [8, 16, 34, 10, 12, 28, 48, 38]
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.freeze_panes = "A2"
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _topic(title: str, children: list | None = None) -> dict:
    topic = {"id": str(uuid4()), "class": "topic", "title": title or "未命名"}
    if children:
        topic["children"] = {"attached": children}
    return topic


def export_xmind(payload: dict) -> BytesIO:
    modules: dict[str, list] = {}
    for case in payload.get("cases", []):
        steps = [_topic(f"步骤 {i}：{step}") for i, step in enumerate(case.get("steps", []), 1)]
        details = [
            _topic(f"优先级：{case.get('priority', '')}"),
            _topic(f"类型：{case.get('type', '')}"),
            _topic(f"前置条件：{case.get('preconditions', '')}"),
            _topic("测试步骤", steps),
            _topic(f"预期结果：{case.get('expected_result', '')}"),
        ]
        modules.setdefault(case.get("module") or "未分类", []).append(_topic(case.get("title", "测试用例"), details))
    root_children = [_topic(module, cases) for module, cases in modules.items()]
    sheet_id = str(uuid4())
    content = [{
        "id": sheet_id,
        "class": "sheet",
        "title": payload.get("suite_name", "测试用例"),
        "rootTopic": _topic(payload.get("suite_name", "测试用例"), root_children),
    }]
    metadata = {"creator": {"name": "TestPilot", "version": "0.2.0"}, "activeSheetId": sheet_id}
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}}}
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.json", json.dumps(content, ensure_ascii=False))
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    output.seek(0)
    return output
