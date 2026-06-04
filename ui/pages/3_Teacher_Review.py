"""Teacher page — review submitted attempts, override scores, finalise.

Flow: pick a notebook → quiz → attempt, inspect each answer's auto-grade, override
where needed, then finalise. Finalisation commits ``final_score`` (teacher override
if present, else auto score) and is the only point a grade becomes official.
"""

from __future__ import annotations

from lib.api import ApiError
from lib.auth import get_client, require_role
import streamlit as st

require_role("teacher")
st.title("✅ Teacher · Review & Finalise")

client = get_client()
assert client is not None


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:g}"


try:
    notebooks = client.list_notebooks()
except ApiError as exc:
    st.error(f"Could not load notebooks — {exc.detail}")
    st.stop()

if not notebooks:
    st.info("No notebooks yet.")
    st.stop()

nb_labels = {f"{nb['title']} ({nb['id'][:8]})": nb for nb in notebooks}
notebook = nb_labels[st.selectbox("Notebook", list(nb_labels))]

try:
    quizzes = client.list_quizzes(notebook["id"])
except ApiError as exc:
    st.error(f"Could not load quizzes — {exc.detail}")
    st.stop()

if not quizzes:
    st.info("No quizzes for this notebook.")
    st.stop()

quiz_labels = {f"{q['title']} — {q['status']}": q for q in quizzes}
quiz = quiz_labels[st.selectbox("Quiz", list(quiz_labels))]

try:
    attempts = client.list_attempts(quiz["id"])
except ApiError as exc:
    st.error(f"Could not load attempts — {exc.detail}")
    st.stop()

if not attempts:
    st.info("No attempts submitted for this quiz yet.")
    st.stop()

att_labels = {f"{a['student_id'][:8]}… — {a['status']}": a for a in attempts}
attempt = att_labels[st.selectbox("Attempt", list(att_labels))]
st.caption(f"Attempt `{attempt['id']}` · student `{attempt['student_id']}` · {attempt['status']}")

try:
    answers = client.get_attempt_answers(attempt["id"])
except ApiError as exc:
    st.error(f"Could not load answers — {exc.detail}")
    st.stop()

if not answers:
    st.info("This attempt has no answers (not submitted yet).")
    st.stop()

st.subheader("Answers")
for ans in answers:
    st.markdown(f"**{ans['ordinal'] + 1}. ({ans['type']})** {ans['stem']}")
    st.markdown(f"*Response:* `{ans['response']}`")
    cols = st.columns(3)
    cols[0].metric("Auto", _fmt(ans["auto_score"]))
    cols[1].metric("Teacher", _fmt(ans["teacher_score"]))
    cols[2].metric("Final", _fmt(ans["final_score"]))
    if ans.get("auto_feedback"):
        st.caption(f"Auto feedback: {ans['auto_feedback']}")

    with st.form(f"override_{ans['answer_id']}"):
        new_score = st.number_input(
            "Override score",
            min_value=0.0,
            value=float(ans["teacher_score"] or ans["auto_score"] or 0.0),
            step=0.5,
            key=f"score_{ans['answer_id']}",
        )
        feedback = st.text_input("Feedback (optional)", key=f"fb_{ans['answer_id']}")
        if st.form_submit_button("Save override"):
            try:
                client.override_answer_score(
                    attempt_id=attempt["id"],
                    answer_id=ans["answer_id"],
                    score=float(new_score),
                    feedback=feedback or None,
                )
                st.success("Override saved.")
                st.rerun()
            except ApiError as exc:
                st.error(f"Override failed — {exc.detail}")
    st.divider()

st.subheader("Finalise")
st.caption("Commits final scores (teacher override where set, else auto score).")
if st.button("Finalise attempt", type="primary"):
    try:
        result = client.finalize_attempt(attempt["id"])
        st.success(f"Finalised. Total score: {result['total_score']:g}")
        st.rerun()
    except ApiError as exc:
        st.error(f"Finalise failed — {exc.detail}")
