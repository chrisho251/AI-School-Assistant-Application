"""Offline route tests — auth/authz wiring and delegation, no DB or LLM.

Strategy: override the auth + DB dependencies and monkeypatch the repository
classes and domain orchestrators referenced by each router, so we exercise the
HTTP layer (status codes, role guards, request/response shapes) in isolation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
import uuid

from fastapi.testclient import TestClient
import pytest

from asag.api import deps
from asag.api.deps import AuthContext, get_db, get_pool, verify_jwt
from asag.api.main import app

TEACHER = AuthContext(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="teacher")
STUDENT = AuthContext(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="student")


async def _fake_db() -> AsyncIterator[object]:
    yield object()  # repos are monkeypatched to ignore the connection


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with pool + DB overridden; auth set per-test via _login()."""
    app.dependency_overrides[get_pool] = lambda: object()
    app.dependency_overrides[get_db] = _fake_db
    # Constructed without a context manager so the lifespan (real pool) never runs.
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(auth: AuthContext) -> None:
    app.dependency_overrides[verify_jwt] = lambda: auth


# --------------------------------------------------------------------------- #
# Meta + auth enforcement                                                      #
# --------------------------------------------------------------------------- #


def test_health_needs_no_auth(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_protected_route_without_token_is_rejected(client: TestClient) -> None:
    # verify_jwt not overridden → HTTPBearer rejects the missing Authorization header.
    assert client.get("/notebooks").status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Notebooks                                                                    #
# --------------------------------------------------------------------------- #


def test_list_notebooks_returns_rows(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(TEACHER)
    nb = {
        "id": uuid.uuid4(),
        "class_id": uuid.uuid4(),
        "owner_id": TEACHER.user_id,
        "title": "NB",
        "subject": None,
        "description": None,
    }

    class FakeRepo:
        def __init__(self, db: Any) -> None: ...
        async def list_for_user(self) -> list[dict[str, Any]]:
            return [nb]

    monkeypatch.setattr("asag.api.routers.notebooks.NotebookRepository", FakeRepo)
    resp = client.get("/notebooks")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "NB"


def test_create_notebook_forbidden_for_student(client: TestClient) -> None:
    _login(STUDENT)
    resp = client.post("/notebooks", json={"class_id": str(uuid.uuid4()), "title": "X"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Quizzes                                                                      #
# --------------------------------------------------------------------------- #


def _patch_notebook_owner(
    monkeypatch: pytest.MonkeyPatch, module: str, owner_id: uuid.UUID
) -> None:
    class FakeNotebookRepo:
        def __init__(self, db: Any) -> None: ...
        async def get_by_id(self, nid: uuid.UUID) -> dict[str, Any]:
            return {"id": nid, "owner_id": owner_id}

    monkeypatch.setattr(f"{module}.NotebookRepository", FakeNotebookRepo)


def test_generate_quiz_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(TEACHER)
    _patch_notebook_owner(monkeypatch, "asag.api.routers.quizzes", TEACHER.user_id)

    notebook_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    fake_quiz = SimpleNamespace(id=quiz_id, notebook_id=notebook_id, title="Q1", status="draft")

    async def fake_generate(nid: uuid.UUID, config: Any, **kw: Any) -> Any:
        return fake_quiz

    monkeypatch.setattr("asag.api.routers.quizzes.generate_quiz", fake_generate)
    resp = client.post(
        "/quizzes/generate",
        json={"notebook_id": str(notebook_id), "title": "Q1", "mix": {"mcq": 3}},
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == str(quiz_id)


def test_publish_quiz_forbidden_for_student(client: TestClient) -> None:
    _login(STUDENT)
    resp = client.patch(f"/quizzes/{uuid.uuid4()}/publish")
    assert resp.status_code == 403


def test_publish_quiz_404_when_not_creator(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(TEACHER)

    class FakeRepo:
        def __init__(self, db: Any) -> None: ...
        async def set_quiz_status(self, qid: uuid.UUID, status: str) -> bool:
            return False  # RLS updated 0 rows → not creator / missing

    monkeypatch.setattr("asag.api.routers.quizzes.AssessmentApiRepository", FakeRepo)
    resp = client.patch(f"/quizzes/{uuid.uuid4()}/publish")
    assert resp.status_code == 404


def test_publish_quiz_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(TEACHER)
    qid = uuid.uuid4()

    class FakeRepo:
        def __init__(self, db: Any) -> None: ...
        async def set_quiz_status(self, q: uuid.UUID, status: str) -> bool:
            return True

        async def get_quiz(self, q: uuid.UUID) -> dict[str, Any]:
            return {"id": qid, "notebook_id": uuid.uuid4(), "title": "Q", "status": "published"}

    monkeypatch.setattr("asag.api.routers.quizzes.AssessmentApiRepository", FakeRepo)
    resp = client.patch(f"/quizzes/{qid}/publish")
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


def test_generate_quiz_rejects_non_owner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(TEACHER)
    _patch_notebook_owner(monkeypatch, "asag.api.routers.quizzes", uuid.uuid4())  # someone else
    resp = client.post(
        "/quizzes/generate",
        json={"notebook_id": str(uuid.uuid4()), "title": "Q1", "mix": {"mcq": 3}},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Attempts                                                                     #
# --------------------------------------------------------------------------- #


def test_start_attempt_requires_published_quiz(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(STUDENT)

    class FakeRepo:
        def __init__(self, db: Any) -> None: ...
        async def get_quiz(self, qid: uuid.UUID) -> dict[str, Any]:
            return {"id": qid, "status": "draft"}  # not published

    monkeypatch.setattr("asag.api.routers.attempts.AssessmentApiRepository", FakeRepo)
    resp = client.post("/attempts/start", json={"quiz_id": str(uuid.uuid4())})
    assert resp.status_code == 400


def test_submit_attempt_triggers_grading(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(STUDENT)
    attempt_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    submitted: list[Any] = []

    class FakeRepo:
        def __init__(self, db: Any) -> None: ...
        async def get_attempt(self, aid: uuid.UUID) -> dict[str, Any]:
            return {
                "id": aid,
                "quiz_id": quiz_id,
                "student_id": STUDENT.user_id,
                "status": "in_progress",
            }

        async def submit_answers(self, aid: uuid.UUID, answers: Any) -> None:
            submitted.append((aid, answers))

    graded: list[uuid.UUID] = []

    async def fake_grade(aid: uuid.UUID, **kw: Any) -> dict[Any, Any]:
        graded.append(aid)
        return {}

    @asynccontextmanager
    async def fake_rls(pool: Any, auth: Any) -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr("asag.api.routers.attempts.rls_connection", fake_rls)
    monkeypatch.setattr("asag.api.routers.attempts.AssessmentApiRepository", FakeRepo)
    monkeypatch.setattr("asag.api.routers.attempts.grade_attempt", fake_grade)

    resp = client.post(
        f"/attempts/{attempt_id}/submit",
        json={"answers": [{"question_id": str(uuid.uuid4()), "response": {"key": "A"}}]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"
    assert submitted  # answers persisted
    assert graded == [attempt_id]  # background grading fired


def test_submit_attempt_rejects_other_students_attempt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(STUDENT)

    class FakeRepo:
        def __init__(self, db: Any) -> None: ...
        async def get_attempt(self, aid: uuid.UUID) -> dict[str, Any]:
            return {
                "id": aid,
                "quiz_id": uuid.uuid4(),
                "student_id": uuid.uuid4(),  # different student
                "status": "in_progress",
            }

    @asynccontextmanager
    async def fake_rls(pool: Any, auth: Any) -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr("asag.api.routers.attempts.rls_connection", fake_rls)
    monkeypatch.setattr("asag.api.routers.attempts.AssessmentApiRepository", FakeRepo)
    resp = client.post(
        f"/attempts/{uuid.uuid4()}/submit",
        json={"answers": []},
    )
    assert resp.status_code == 403


def test_finalize_forbidden_for_student(client: TestClient) -> None:
    _login(STUDENT)
    resp = client.post(f"/attempts/{uuid.uuid4()}/finalize")
    assert resp.status_code == 403


def test_finalize_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(TEACHER)

    async def fake_finalize(aid: uuid.UUID, tid: uuid.UUID, **kw: Any) -> float:
        return 7.5

    monkeypatch.setattr("asag.api.routers.attempts.finalize_attempt", fake_finalize)
    resp = client.post(f"/attempts/{uuid.uuid4()}/finalize")
    assert resp.status_code == 200
    assert resp.json() == {"total_score": 7.5}


# --------------------------------------------------------------------------- #
# Chat SSE                                                                     #
# --------------------------------------------------------------------------- #


def test_chat_streams_tokens(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(STUDENT)
    notebook_id = uuid.uuid4()

    @asynccontextmanager
    async def fake_rls(pool: Any, auth: Any) -> AsyncIterator[object]:
        yield object()

    class FakeNotebookRepo:
        def __init__(self, db: Any) -> None: ...
        async def get_by_id(self, nid: uuid.UUID) -> dict[str, Any]:
            return {"id": nid}

    async def fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        for tok in ("Hello", " world"):
            yield tok

    monkeypatch.setattr("asag.api.routers.chat.rls_connection", fake_rls)
    monkeypatch.setattr("asag.api.routers.chat.NotebookRepository", FakeNotebookRepo)
    monkeypatch.setattr("asag.api.routers.chat.stream_answer", fake_stream)
    # Avoid touching real embedding/reranker clients in app.state.
    app.dependency_overrides[deps.get_embed_client] = lambda: object()
    app.dependency_overrides[deps.get_rerank_client] = lambda: object()

    resp = client.get(f"/chat/{notebook_id}", params={"q": "hi"})
    assert resp.status_code == 200
    body = resp.text
    assert "Hello" in body and "world" in body
    assert "event: done" in body


def test_chat_404_for_invisible_notebook(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(STUDENT)

    @asynccontextmanager
    async def fake_rls(pool: Any, auth: Any) -> AsyncIterator[object]:
        yield object()

    class FakeNotebookRepo:
        def __init__(self, db: Any) -> None: ...
        async def get_by_id(self, nid: uuid.UUID) -> None:
            return None

    monkeypatch.setattr("asag.api.routers.chat.rls_connection", fake_rls)
    monkeypatch.setattr("asag.api.routers.chat.NotebookRepository", FakeNotebookRepo)
    app.dependency_overrides[deps.get_embed_client] = lambda: object()
    app.dependency_overrides[deps.get_rerank_client] = lambda: object()

    resp = client.get(f"/chat/{uuid.uuid4()}", params={"q": "hi"})
    assert resp.status_code == 404
