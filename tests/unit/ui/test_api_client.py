"""Unit tests for the Streamlit ApiClient — request shaping + error handling.

Uses an httpx MockTransport so no live backend is needed: we assert the client
hits the right path/method, attaches the bearer token, and raises ApiError with
the server's detail on a non-2xx response.
"""

from __future__ import annotations

import json
import uuid

import httpx
from lib.api import ApiClient, ApiError
import pytest


def _client_with(handler: httpx.MockTransport) -> ApiClient:
    """Build an ApiClient whose underlying httpx.Client uses *handler*."""
    client = ApiClient("dev.u.o.teacher", base_url="http://test")
    client._client = httpx.Client(
        transport=handler,
        base_url="http://test",
        headers={"Authorization": "Bearer dev.u.o.teacher"},
    )
    return client


def test_list_notebooks_sends_auth_header() -> None:
    captured: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        captured["path"] = request.url.path
        return httpx.Response(200, json=[{"id": "1", "title": "NB"}])

    client = _client_with(httpx.MockTransport(handle))
    result = client.list_notebooks()

    assert captured["auth"] == "Bearer dev.u.o.teacher"
    assert captured["path"] == "/notebooks"
    assert result[0]["title"] == "NB"


def test_create_notebook_posts_json_body() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["method"] = request.method
        return httpx.Response(201, json={"id": "n1", "title": "T"})

    client = _client_with(httpx.MockTransport(handle))
    client.create_notebook(class_id="c1", title="T", subject="math")

    assert captured["method"] == "POST"
    assert captured["body"] == {
        "class_id": "c1",
        "title": "T",
        "subject": "math",
        "description": None,
    }


def test_upload_source_sends_multipart() -> None:
    captured: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["ctype"] = request.headers.get("content-type", "")
        return httpx.Response(202, json={"id": "s1", "ingestion_status": "pending"})

    client = _client_with(httpx.MockTransport(handle))
    out = client.upload_source(
        notebook_id="n1", filename="a.pdf", data=b"%PDF", content_type="application/pdf"
    )

    assert captured["ctype"].startswith("multipart/form-data")
    assert out["ingestion_status"] == "pending"


def test_override_answer_score_uses_patch_and_path() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    client = _client_with(httpx.MockTransport(handle))
    client.override_answer_score(attempt_id="att", answer_id="ans", score=2.5, feedback="ok")

    assert captured["method"] == "PATCH"
    assert captured["path"] == "/attempts/att/answers/ans/score"
    assert captured["body"] == {"score": 2.5, "feedback": "ok"}


def test_non_2xx_raises_api_error_with_detail() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Teacher role required"})

    client = _client_with(httpx.MockTransport(handle))
    with pytest.raises(ApiError) as exc:
        client.list_notebooks()

    assert exc.value.status_code == 403
    assert exc.value.detail == "Teacher role required"


def test_stream_chat_yields_token_events() -> None:
    sse = "event: token\ndata: Hello\n\nevent: token\ndata:  world\n\nevent: done\ndata: \n\n"

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "hi"
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    client = _client_with(httpx.MockTransport(handle))
    tokens = list(client.stream_chat(notebook_id=str(uuid.uuid4()), question="hi"))

    assert tokens == ["Hello", " world"]


def test_stream_chat_raises_on_error_event() -> None:
    sse = "event: error\ndata: ValueError: boom\n\n"

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    client = _client_with(httpx.MockTransport(handle))
    with pytest.raises(ApiError):
        list(client.stream_chat(notebook_id=str(uuid.uuid4()), question="hi"))
