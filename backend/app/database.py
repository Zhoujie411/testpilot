from pathlib import Path
import sqlite3
import os


DB_PATH = Path(__file__).resolve().parent.parent / "testpilot.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS environments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                base_url TEXT NOT NULL,
                variables_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                total INTEGER NOT NULL DEFAULT 0,
                passed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS model_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'openai_compatible',
                base_url TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
                model_name TEXT NOT NULL,
                api_key_ciphertext TEXT NOT NULL,
                api_style TEXT NOT NULL DEFAULT 'chat_completions',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ai_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '新会话',
                model_config_id INTEGER,
                memory_summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(model_config_id) REFERENCES model_configs(id)
            );
            CREATE TABLE IF NOT EXISTS ai_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                structured_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES ai_sessions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS ai_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                content_text TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES ai_sessions(id) ON DELETE CASCADE
            );
            """
        )
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(ai_sessions)").fetchall()
        }
        if "owner_id" not in columns:
            connection.execute("ALTER TABLE ai_sessions ADD COLUMN owner_id INTEGER REFERENCES users(id)")
        _bootstrap_admin(connection)


def _bootstrap_admin(connection: sqlite3.Connection) -> None:
    username = os.getenv("TESTPILOT_ADMIN_USERNAME", "").strip()
    password = os.getenv("TESTPILOT_ADMIN_PASSWORD", "")
    if not username or not password:
        return
    if len(password) < 12:
        raise RuntimeError("TESTPILOT_ADMIN_PASSWORD 至少需要 12 个字符")
    existing = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing is None:
        from app.auth import hash_password

        cursor = connection.execute(
            """INSERT INTO users(username, display_name, password_hash, role)
            VALUES (?, ?, ?, 'admin')""",
            (username, "系统管理员", hash_password(password)),
        )
        admin_id = cursor.lastrowid
    else:
        admin_id = existing["id"]
        connection.execute("UPDATE users SET role = 'admin', is_active = 1 WHERE id = ?", (admin_id,))
    connection.execute("UPDATE ai_sessions SET owner_id = ? WHERE owner_id IS NULL", (admin_id,))
