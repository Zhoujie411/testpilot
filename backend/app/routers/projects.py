import json

from fastapi import APIRouter, HTTPException

from app.database import get_connection
from app.models import (
    Environment,
    EnvironmentCreate,
    Project,
    ProjectCreate,
    TestCase,
    TestCaseCreate,
    TestRun,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[Project])
def list_projects():
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


@router.post("", response_model=Project, status_code=201)
def create_project(payload: ProjectCreate):
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO projects(name, description) VALUES (?, ?)",
            (payload.name, payload.description),
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def ensure_project(project_id: int) -> None:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")


@router.get("/{project_id}/environments", response_model=list[Environment])
def list_environments(project_id: int):
    ensure_project(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM environments WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
    return [
        {**dict(row), "variables": json.loads(row["variables_json"])}
        for row in rows
    ]


@router.post("/{project_id}/environments", response_model=Environment, status_code=201)
def create_environment(project_id: int, payload: EnvironmentCreate):
    ensure_project(project_id)
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO environments(project_id, name, base_url, variables_json) VALUES (?, ?, ?, ?)",
            (project_id, payload.name, payload.base_url, json.dumps(payload.variables)),
        )
        row = connection.execute(
            "SELECT * FROM environments WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return {**dict(row), "variables": json.loads(row["variables_json"])}


@router.get("/{project_id}/test-cases", response_model=list[TestCase])
def list_test_cases(project_id: int):
    ensure_project(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM test_cases WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/{project_id}/test-cases", response_model=TestCase, status_code=201)
def create_test_case(project_id: int, payload: TestCaseCreate):
    ensure_project(project_id)
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO test_cases(project_id, name, method, path) VALUES (?, ?, ?, ?)",
            (project_id, payload.name, payload.method.upper(), payload.path),
        )
        row = connection.execute(
            "SELECT * FROM test_cases WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


@router.get("/{project_id}/runs", response_model=list[TestRun])
def list_runs(project_id: int):
    ensure_project(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM test_runs WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
    return [dict(row) for row in rows]
