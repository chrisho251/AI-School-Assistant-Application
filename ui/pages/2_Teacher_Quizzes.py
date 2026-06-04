"""Teacher page — generate a quiz from a notebook, review its questions, publish.

Generation is grounded on the notebook's ingested chunks (backend enforces
``source_chunk_ids``); this page only collects the mix/difficulty and renders the
resulting draft. Editing question text is out of POC scope — review + publish only.
"""

from __future__ import annotations

from lib.api import ApiError
from lib.auth import get_client, require_role
import streamlit as st

require_role("teacher")
st.title("📝 Teacher · Quizzes")

client = get_client()
assert client is not None

try:
    notebooks = client.list_notebooks()
except ApiError as exc:
    st.error(f"Could not load notebooks — {exc.detail}")
    st.stop()

if not notebooks:
    st.info("Create a notebook and ingest a PDF first (Teacher Notebooks page).")
    st.stop()

labels = {f"{nb['title']} ({nb['id'][:8]})": nb for nb in notebooks}
notebook = labels[st.selectbox("Notebook", list(labels))]

# --------------------------------------------------------------------------- #
# Generate                                                                    #
# --------------------------------------------------------------------------- #

with st.expander("➕ Generate a quiz", expanded=False), st.form("generate_quiz"):
    title = st.text_input("Quiz title", value="Untitled quiz")
    n_mcq = st.number_input("MCQ questions", min_value=0, max_value=20, value=5)
    n_short = st.number_input("Short-answer questions", min_value=0, max_value=20, value=0)
    difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"], index=1)
    if st.form_submit_button("Generate (may take ~30s)"):
        mix = {k: v for k, v in {"mcq": int(n_mcq), "short": int(n_short)}.items() if v > 0}
        if not mix:
            st.error("Request at least one question.")
        else:
            with st.spinner("Generating grounded questions…"):
                try:
                    quiz = client.generate_quiz(
                        notebook_id=notebook["id"],
                        title=title,
                        mix=mix,
                        difficulty=difficulty,
                    )
                    st.success(f"Generated draft '{quiz['title']}' ({quiz['status']}).")
                    st.rerun()
                except ApiError as exc:
                    st.error(f"Generation failed — {exc.detail}")

# --------------------------------------------------------------------------- #
# List + review + publish                                                     #
# --------------------------------------------------------------------------- #

try:
    quizzes = client.list_quizzes(notebook["id"])
except ApiError as exc:
    st.error(f"Could not load quizzes — {exc.detail}")
    st.stop()

if not quizzes:
    st.info("No quizzes for this notebook yet.")
    st.stop()

st.subheader("Quizzes")
for quiz in quizzes:
    with st.expander(f"{quiz['title']} — {quiz['status']}"):
        try:
            full = client.get_quiz(quiz["id"])
        except ApiError as exc:
            st.error(f"Could not load quiz — {exc.detail}")
            continue

        for q in full.get("questions", []):
            flag = " ⚠️ needs review" if q.get("needs_review") else ""
            st.markdown(f"**{q['ordinal'] + 1}. ({q['type']}){flag}** {q['stem']}")
            for opt in q.get("options") or []:
                st.markdown(f"- `{opt['key']}` {opt['text']}")

        if quiz["status"] == "draft":
            if st.button("Publish", key=f"pub_{quiz['id']}"):
                try:
                    client.publish_quiz(quiz["id"])
                    st.success("Published.")
                    st.rerun()
                except ApiError as exc:
                    st.error(f"Publish failed — {exc.detail}")
        else:
            st.caption(f"Status: {quiz['status']} · ID `{quiz['id']}`")
