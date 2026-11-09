from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from app.database import get_connection


router = APIRouter(prefix="/api/auth", tags=["authentication"])
admin_router = APIRouter(prefix="/api/admin", tags=["administration"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=3, max_length=40)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=200)
    role: str = "user"


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    password: str | None = Field(default=None, min_length=12, max_length=200)
    role: str | None = None
    is_active: bool | None = None


def public_user(row) -> dict:
    return dict(row)


@router.post("/login")
def login(payload: LoginRequest):
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM users WHERE username = ?", (payload.username,)).fetchone()
    if row is None or not row["is_active"] or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user = dict(row)
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": {key: user[key] for key in ("id", "username", "display_name", "role", "is_active")},
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


@admin_router.get("/users")
def list_users(_: dict = Depends(require_admin)):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, username, display_name, role, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
    return [public_user(row) for row in rows]


@admin_router.post("/users", status_code=201)
def create_user(payload: UserCreate, _: dict = Depends(require_admin)):
    if payload.role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="角色无效")
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """INSERT INTO users(username, display_name, password_hash, role)
                VALUES (?, ?, ?, ?)""",
                (payload.username, payload.display_name, hash_password(payload.password), payload.role),
            )
            row = connection.execute(
                "SELECT id, username, display_name, role, is_active, created_at FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            raise HTTPException(status_code=409, detail="用户名已存在") from error
        raise
    return public_user(row)


@admin_router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, admin: dict = Depends(require_admin)):
    if payload.role is not None and payload.role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="角色无效")
    if user_id == admin["id"] and (payload.role == "user" or payload.is_active is False):
        raise HTTPException(status_code=400, detail="不能降级或停用当前管理员账号")
    fields = []
    values = []
    for name in ("display_name", "role"):
        value = getattr(payload, name)
        if value is not None:
            fields.append(f"{name} = ?")
            values.append(value)
    if payload.password is not None:
        fields.append("password_hash = ?")
        values.append(hash_password(payload.password))
    if payload.is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if payload.is_active else 0)
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要更新的内容")
    values.append(user_id)
    with get_connection() as connection:
        cursor = connection.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="用户不存在")
        row = connection.execute(
            "SELECT id, username, display_name, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return public_user(row)
