"""Synchronous httpx wrapper for the ASAG FastAPI backend.

One ``ApiClient`` per logged-in session; the bearer token is attached to every
request. Streamlit runs synchronously, so this uses ``httpx.Client`` (not async).
Methods mirror the FastAPI routes 1:1 and raise ``ApiError`` on non-2xx so pages
can surface a clean message instead of a traceback.
"""

from __future__ import annotations

from collections.abc import Iterator
import os
from typing import Any
import uuid

import httpx

DEFAULT_BASE_URL = os.environ.get("ASAG_API_URL", "http://localhost:8000")


class ApiError(RuntimeError):
    """A non-2xx response from the backend, carrying status + server detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _detail(resp: httpx.Response) -> str:
    """Best-effort extraction of FastAPI's ``detail`` field from an error body."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text or resp.reason_phrase
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)


class ApiClient:
    """Typed client over the ASAG API for one authenticated user.

    Args:
        token:    Bearer token (Supabase JWT or a ``dev.*`` token in dev mode).
        base_url: API origin; defaults to ``$ASAG_API_URL`` or localhost:8000.
        timeout:  Per-request timeout in seconds.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    # ----------------------------------------------------------------- #
    # Internals                                                         #
    # ----------------------------------------------------------------- #

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Issue a request and return parsed JSON, or raise ``ApiError``."""
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, _detail(resp))
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    # ----------------------------------------------------------------- #
    # Meta                                                              #
    # ----------------------------------------------------------------- #

    def health(self) -> dict[str, str]:
        """Liveness probe — used to verify the backend is reachable."""
        return self._request("GET", "/health")  # type: ignore[no-any-return]

    # ----------------------------------------------------------------- #
    # Notebooks                                                         #
    # ----------------------------------------------------------------- #

    def list_notebooks(self) -> list[dict[str, Any]]:
        """List notebooks visible to the caller."""
        return self._request("GET", "/notebooks")  # type: ignore[no-any-return]

    def get_notebook(self, notebook_id: uuid.UUID | str) -> dict[str, Any]:
        """Fetch one notebook by id."""
        return self._request("GET", f"/notebooks/{notebook_id}")  # type: ignore[no-any-return]

    def create_notebook(
        self,
        *,
        class_id: uuid.UUID | str,
        title: str,
        subject: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a notebook under a class the caller teaches."""
        payload = {
            "class_id": str(class_id),
            "title": title,
            "subject": subject,
            "description": description,
        }
        return self._request("POST", "/notebooks", json=payload)  # type: ignore[no-any-return]

    # ----------------------------------------------------------------- #
    # Sources                                                           #
    # ----------------------------------------------------------------- #

    def upload_source(
        self,
        *,
        notebook_id: uuid.UUID | str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload a PDF/image to a notebook; returns the pending source row."""
        return self._request(  # type: ignore[no-any-return]
            "POST",
            "/sources",
            data={"notebook_id": str(notebook_id)},
            files={"file": (filename, data, content_type)},
        )

    def list_sources(self, notebook_id: uuid.UUID | str) -> list[dict[str, Any]]:
        """List a notebook's sources with ingestion status (for polling)."""
        return self._request("GET", f"/sources/notebook/{notebook_id}")  # type: ignore[no-any-return]

    # ----------------------------------------------------------------- #
    # Quizzes                                                           #
    # ----------------------------------------------------------------- #

    def generate_quiz(
        self,
        *,
        notebook_id: uuid.UUID | str,
        title: str,
        mix: dict[str, int],
        difficulty: str = "medium",
    ) -> dict[str, Any]:
        """Generate a draft quiz from a notebook's chunks."""
        payload = {
            "notebook_id": str(notebook_id),
            "title": title,
            "mix": mix,
            "difficulty": difficulty,
        }
        return self._request("POST", "/quizzes/generate", json=payload)  # type: ignore[no-any-return]

    def list_quizzes(self, notebook_id: uuid.UUID | str) -> list[dict[str, Any]]:
        """List quizzes for a notebook."""
        return self._request("GET", f"/quizzes/notebook/{notebook_id}")  # type: ignore[no-any-return]

    def get_quiz(self, quiz_id: uuid.UUID | str) -> dict[str, Any]:
        """Fetch a quiz header plus its questions (no answer key)."""
        return self._request("GET", f"/quizzes/{quiz_id}")  # type: ignore[no-any-return]

    def publish_quiz(self, quiz_id: uuid.UUID | str) -> dict[str, Any]:
        """Publish a draft quiz so students can attempt it."""
        return self._request("PATCH", f"/quizzes/{quiz_id}/publish")  # type: ignore[no-any-return]

    # ----------------------------------------------------------------- #
    # Attempts + review                                                 #
    # ----------------------------------------------------------------- #

    def start_attempt(self, quiz_id: uuid.UUID | str) -> dict[str, Any]:
        """Start an attempt on a published quiz."""
        return self._request("POST", "/attempts/start", json={"quiz_id": str(quiz_id)})  # type: ignore[no-any-return]

    def submit_attempt(
        self, attempt_id: uuid.UUID | str, answers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Submit answers for an in-progress attempt (triggers async grading)."""
        return self._request(  # type: ignore[no-any-return]
            "POST", f"/attempts/{attempt_id}/submit", json={"answers": answers}
        )

    def get_attempt(self, attempt_id: uuid.UUID | str) -> dict[str, Any]:
        """Fetch an attempt's current state."""
        return self._request("GET", f"/attempts/{attempt_id}")  # type: ignore[no-any-return]

    def list_attempts(self, quiz_id: uuid.UUID | str) -> list[dict[str, Any]]:
        """List attempts on a quiz (teacher review)."""
        return self._request("GET", f"/attempts/quiz/{quiz_id}")  # type: ignore[no-any-return]

    def get_attempt_answers(self, attempt_id: uuid.UUID | str) -> list[dict[str, Any]]:
        """Fetch an attempt's answers with scores (teacher review)."""
        return self._request("GET", f"/attempts/{attempt_id}/answers")  # type: ignore[no-any-return]

    def override_answer_score(
        self,
        *,
        attempt_id: uuid.UUID | str,
        answer_id: uuid.UUID | str,
        score: float,
        feedback: str | None = None,
    ) -> dict[str, str]:
        """Override one answer's score (teacher)."""
        return self._request(  # type: ignore[no-any-return]
            "PATCH",
            f"/attempts/{attempt_id}/answers/{answer_id}/score",
            json={"score": score, "feedback": feedback},
        )

    def finalize_attempt(self, attempt_id: uuid.UUID | str) -> dict[str, float]:
        """Commit final scores for an attempt (teacher)."""
        return self._request("POST", f"/attempts/{attempt_id}/finalize")  # type: ignore[no-any-return]

    # ----------------------------------------------------------------- #
    # Chat (SSE) — used by the student UI in Day 11                     #
    # ----------------------------------------------------------------- #

    def stream_chat(
        self,
        *,
        notebook_id: uuid.UUID | str,
        question: str,
        conversation_id: uuid.UUID | str | None = None,
    ) -> Iterator[str]:
        """Yield answer tokens from the SSE chat endpoint.

        Raises ``ApiError`` on a non-2xx open or on an ``error`` SSE event so the
        caller can render a clean failure instead of a silently truncated answer.
        """
        params: dict[str, str] = {"q": question}
        if conversation_id is not None:
            params["conversation_id"] = str(conversation_id)
        with self._client.stream("GET", f"/chat/{notebook_id}", params=params) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise ApiError(resp.status_code, _detail(resp))
            event = "message"
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    # SSE strips exactly one optional leading space after the colon.
                    data = line[len("data:") :]
                    if data.startswith(" "):
                        data = data[1:]
                    if event == "error":
                        raise ApiError(502, data)
                    if event == "token":
                        yield data
                elif line == "":
                    event = "message"  # blank line terminates one SSE event
