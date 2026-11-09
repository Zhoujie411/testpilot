import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai_agent import build_model, run_test_case_agent
from app.ai_export import export_excel, export_xmind
from app.ai_security import decrypt_api_key, encrypt_api_key
from app.attachment_parser import SUPPORTED_SUFFIXES, compact_attachment_context, extract_text
from app.auth import get_current_user, require_admin
from app.database import get_connection
from app.url_fetch import fetch_url_text


router = APIRouter(prefix="/api/ai", tags=["ai-agent"])
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024


class ModelConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=1)
    api_style: str = "chat_completions"


class SessionCreate(BaseModel):
    title: str = "新会话"
    model_config_id: int | None = None


class SessionUpdate(BaseModel):
    model_config_id: int


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class LinkCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


def _row(row) -> dict:
    return dict(row) if row else {}


def _get_session(session_id: int, user: dict) -> dict:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM ai_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if user["role"] != "admin" and row["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    return _row(row)


def _public_model(row) -> dict:
    item = _row(row)
    item.pop("api_key_ciphertext", None)
    item["has_api_key"] = True
    return item


@router.get("/models")
def list_models(_: dict = Depends(get_current_user)):
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM model_configs ORDER BY id DESC").fetchall()
    return [_public_model(row) for row in rows]


@router.post("/models", status_code=201)
def create_model(payload: ModelConfigCreate, _: dict = Depends(require_admin)):
    if payload.api_style not in {"chat_completions", "responses"}:
        raise HTTPException(status_code=400, detail="API 模式无效")
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO model_configs
            (name, provider, base_url, model_name, api_key_ciphertext, api_style)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                payload.name,
                payload.provider,
                payload.base_url.rstrip("/"),
                payload.model_name,
                encrypt_api_key(payload.api_key),
                payload.api_style,
            ),
        )
        row = connection.execute("SELECT * FROM model_configs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _public_model(row)


@router.post("/models/{model_id}/test")
def test_model(model_id: int, _: dict = Depends(require_admin)):
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM model_configs WHERE id = ?", (model_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    config = _row(row)
    try:
        response = build_model(config, decrypt_api_key(config["api_key_ciphertext"])).invoke(
            "仅回复 OK，用于连通性测试。"
        )
        return {"ok": True, "message": str(response.content)[:200]}
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"模型连接失败：{error}") from error


@router.get("/sessions")
def list_sessions(user: dict = Depends(get_current_user)):
    with get_connection() as connection:
        if user["role"] == "admin":
            rows = connection.execute(
                """SELECT s.*, m.name AS model_name, u.username AS owner_username
                FROM ai_sessions s
                LEFT JOIN model_configs m ON s.model_config_id = m.id
                LEFT JOIN users u ON s.owner_id = u.id
                ORDER BY s.updated_at DESC, s.id DESC"""
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT s.*, m.name AS model_name, u.username AS owner_username
                FROM ai_sessions s
                LEFT JOIN model_configs m ON s.model_config_id = m.id
                LEFT JOIN users u ON s.owner_id = u.id
                WHERE s.owner_id = ? ORDER BY s.updated_at DESC, s.id DESC""",
                (user["id"],),
            ).fetchall()
    return [_row(row) for row in rows]


@router.post("/sessions", status_code=201)
def create_session(payload: SessionCreate, user: dict = Depends(get_current_user)):
    if payload.model_config_id is not None:
        with get_connection() as connection:
            model = connection.execute(
                "SELECT id FROM model_configs WHERE id = ?", (payload.model_config_id,)
            ).fetchone()
        if model is None:
            raise HTTPException(status_code=404, detail="模型配置不存在")
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO ai_sessions(title, model_config_id, owner_id) VALUES (?, ?, ?)",
            (payload.title, payload.model_config_id, user["id"]),
        )
        row = connection.execute("SELECT * FROM ai_sessions WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row(row)


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, payload: SessionUpdate, user: dict = Depends(get_current_user)):
    _get_session(session_id, user)
    with get_connection() as connection:
        model = connection.execute(
            "SELECT id FROM model_configs WHERE id = ?", (payload.model_config_id,)
        ).fetchone()
        if model is None:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        connection.execute(
            "UPDATE ai_sessions SET model_config_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payload.model_config_id, session_id),
        )
        row = connection.execute("SELECT * FROM ai_sessions WHERE id = ?", (session_id,)).fetchone()
    return _row(row)


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: int, user: dict = Depends(get_current_user)):
    _get_session(session_id, user)
    with get_connection() as connection:
        messages = connection.execute(
            "SELECT * FROM ai_messages WHERE session_id = ? ORDER BY id", (session_id,)
        ).fetchall()
        attachments = connection.execute(
            "SELECT id, original_name, size, created_at FROM ai_attachments WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    items = []
    for row in messages:
        item = _row(row)
        item["structured"] = json.loads(item["structured_json"]) if item.get("structured_json") else None
        item.pop("structured_json", None)
        items.append(item)
    return {"messages": items, "attachments": [_row(row) for row in attachments]}


@router.post("/sessions/{session_id}/attachments", status_code=201)
async def upload_attachments(
    session_id: int,
    files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    _get_session(session_id, user)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for upload in files:
        original_name = Path(upload.filename or "attachment").name
        suffix = Path(original_name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"不支持附件格式：{suffix or '未知'}")
        content = await upload.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"{original_name} 超过 10MB")
        stored_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
        stored_path.write_bytes(content)
        try:
            text = extract_text(stored_path)
        except Exception as error:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"解析 {original_name} 失败：{error}") from error
        with get_connection() as connection:
            cursor = connection.execute(
                """INSERT INTO ai_attachments(session_id, original_name, stored_path, content_text, size)
                VALUES (?, ?, ?, ?, ?)""",
                (session_id, original_name, str(stored_path), text, len(content)),
            )
            row = connection.execute(
                "SELECT id, original_name, size, created_at FROM ai_attachments WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        saved.append(_row(row))
    return saved


@router.post("/sessions/{session_id}/links", status_code=201)
def add_session_link(session_id: int, payload: LinkCreate, user: dict = Depends(get_current_user)):
    """抓取需求链接正文，存为会话附件，与上传文件走同一套上下文与检索逻辑。"""
    _get_session(session_id, user)
    try:
        text, final_url, size = fetch_url_text(payload.url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"抓取链接失败：{error}") from error
    original_name = final_url if len(final_url) <= 200 else f"{final_url[:197]}..."
    stored_path = UPLOAD_DIR / f"{uuid4().hex}.txt"
    stored_path.write_text(text, encoding="utf-8")
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO ai_attachments(session_id, original_name, stored_path, content_text, size)
            VALUES (?, ?, ?, ?, ?)""",
            (session_id, original_name, str(stored_path), text, size),
        )
        row = connection.execute(
            "SELECT id, original_name, size, created_at FROM ai_attachments WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return _row(row)


@router.post("/sessions/{session_id}/chat")
def chat(session_id: int, payload: ChatRequest, user: dict = Depends(get_current_user)):
    session = _get_session(session_id, user)
    if session["model_config_id"] is None:
        raise HTTPException(status_code=400, detail="请先为会话选择模型")
    with get_connection() as connection:
        model_row = connection.execute(
            "SELECT * FROM model_configs WHERE id = ?", (session["model_config_id"],)
        ).fetchone()
        if model_row is None:
            raise HTTPException(status_code=404, detail="当前模型配置已不存在")
        connection.execute(
            "INSERT INTO ai_messages(session_id, role, content) VALUES (?, 'user', ?)",
            (session_id, payload.content),
        )
        if session["title"] == "新会话":
            connection.execute(
                "UPDATE ai_sessions SET title = ? WHERE id = ?",
                (payload.content.strip()[:30], session_id),
            )
        history = [
            _row(row)
            for row in connection.execute(
                "SELECT role, content FROM ai_messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        ]
        attachments = [
            _row(row)
            for row in connection.execute(
                "SELECT original_name, content_text FROM ai_attachments WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        ]

    def save_memory(fact: str) -> None:
        clean_fact = fact.strip()[:1000]
        if not clean_fact:
            return
        with get_connection() as memory_connection:
            current_row = memory_connection.execute(
                "SELECT memory_summary FROM ai_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            current = current_row["memory_summary"] or ""
            if clean_fact not in current:
                updated = (current + "\n- " + clean_fact).strip()[-8000:]
                memory_connection.execute(
                    "UPDATE ai_sessions SET memory_summary = ? WHERE id = ?", (updated, session_id)
                )

    try:
        content, structured = run_test_case_agent(
            _row(model_row),
            decrypt_api_key(model_row["api_key_ciphertext"]),
            history,
            compact_attachment_context(attachments),
            session["memory_summary"],
            save_memory,
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Agent 执行失败：{error}") from error

    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO ai_messages(session_id, role, content, structured_json)
            VALUES (?, 'assistant', ?, ?)""",
            (session_id, content, json.dumps(structured, ensure_ascii=False) if structured else None),
        )
        connection.execute(
            "UPDATE ai_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,)
        )
        row = connection.execute("SELECT * FROM ai_messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
    item = _row(row)
    item["structured"] = structured
    item.pop("structured_json", None)
    return item


@router.get("/sessions/{session_id}/export")
def export_cases(
    session_id: int,
    format: str = "xlsx",
    user: dict = Depends(get_current_user),
):
    _get_session(session_id, user)
    with get_connection() as connection:
        row = connection.execute(
            """SELECT structured_json FROM ai_messages
            WHERE session_id = ? AND role = 'assistant' AND structured_json IS NOT NULL
            ORDER BY id DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=409, detail="当前会话还没有可导出的结构化测试用例")
    payload = json.loads(row["structured_json"])
    if format == "xlsx":
        stream = export_excel(payload)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        suffix = "xlsx"
    elif format == "xmind":
        stream = export_xmind(payload)
        media_type = "application/x-xmind"
        suffix = "xmind"
    else:
        raise HTTPException(status_code=400, detail="仅支持 xlsx 或 xmind")
    return StreamingResponse(
        stream,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="test-cases-{session_id}.{suffix}"'},
    )
