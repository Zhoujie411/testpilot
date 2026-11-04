from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""


class Project(ProjectCreate):
    id: int
    created_at: str


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str
    variables: dict[str, str] = Field(default_factory=dict)


class Environment(EnvironmentCreate):
    id: int
    project_id: int


class TestCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    method: str = "GET"
    path: str = "/"


class TestCase(TestCaseCreate):
    id: int
    project_id: int
    status: str


class TestRun(BaseModel):
    id: int
    project_id: int
    status: str
    total: int
    passed: int
    failed: int
    created_at: str
