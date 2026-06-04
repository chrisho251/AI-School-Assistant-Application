"""Streamlit entry — login + role-aware landing for the ASAG UI.

Run: ``uv run streamlit run ui/app.py`` (with the FastAPI backend on $ASAG_API_URL).
Streamlit auto-discovers the ``pages/`` directory; this script handles login and
routes the user to the pages their role can use.
"""

from __future__ import annotations

from lib.auth import login_sidebar
import streamlit as st

st.set_page_config(page_title="ASAG", page_icon="🎓", layout="wide")

st.title("🎓 ASAG — AI School Assistant & Grader")

user = login_sidebar()

if user is None:
    st.info("Log in from the sidebar to begin. Use the IDs seeded for your demo account.")
    st.markdown(
        "- **Teachers** can create notebooks, upload PDFs, generate quizzes, and "
        "review attempts.\n"
        "- **Students** can chat with notebooks and take quizzes (Day 11)."
    )
    st.stop()

st.success(f"Logged in as **{user['role']}** (`{user['user_id']}`).")

if user["role"] == "teacher":
    st.markdown(
        "### Teacher tools\n"
        "Use the pages in the sidebar:\n"
        "1. **Teacher Notebooks** — create notebooks and upload PDFs.\n"
        "2. **Teacher Quizzes** — generate, review, and publish quizzes.\n"
        "3. **Teacher Review** — grade and finalise student attempts."
    )
else:
    st.markdown(
        "### Student tools\n"
        "Chat and quiz pages arrive in Day 11. For now you can verify login works."
    )
