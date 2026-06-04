"""Teacher page — list notebooks, create a notebook, upload a PDF, watch ingestion.

All data access goes through ``ApiClient`` (no business logic here, per CLAUDE.md).
Notebook creation needs a ``class_id``: the POC has no class-management UI, so the
teacher pastes the UUID of a class they teach (seeded by ``scripts/seed_demo.py``).
"""

from __future__ import annotations

from lib.api import ApiError
from lib.auth import get_client, require_role
import streamlit as st

require_role("teacher")
st.title("📓 Teacher · Notebooks")

client = get_client()
assert client is not None  # require_role guarantees a logged-in client

# --------------------------------------------------------------------------- #
# Create notebook                                                             #
# --------------------------------------------------------------------------- #

with st.expander("➕ Create a notebook", expanded=False), st.form("create_notebook"):
    class_id = st.text_input("Class ID (UUID of a class you teach)")
    title = st.text_input("Title")
    subject = st.text_input("Subject (optional)")
    description = st.text_area("Description (optional)")
    if st.form_submit_button("Create"):
        try:
            nb = client.create_notebook(
                class_id=class_id,
                title=title,
                subject=subject or None,
                description=description or None,
            )
            st.success(f"Created notebook '{nb['title']}' ({nb['id']}).")
            st.rerun()
        except ApiError as exc:
            st.error(f"Create failed — {exc.detail}")

# --------------------------------------------------------------------------- #
# Notebook list + upload                                                      #
# --------------------------------------------------------------------------- #

try:
    notebooks = client.list_notebooks()
except ApiError as exc:
    st.error(f"Could not load notebooks — {exc.detail}")
    st.stop()

if not notebooks:
    st.info("No notebooks yet. Create one above.")
    st.stop()

labels = {f"{nb['title']} ({nb['id'][:8]})": nb for nb in notebooks}
choice = st.selectbox("Select a notebook", list(labels))
notebook = labels[choice]
st.caption(f"ID: `{notebook['id']}` · Subject: {notebook.get('subject') or '—'}")

st.subheader("Upload a source (PDF / PNG / JPG)")
uploaded = st.file_uploader("File", type=["pdf", "png", "jpg", "jpeg"])
if uploaded is not None and st.button("Upload + ingest"):
    try:
        src = client.upload_source(
            notebook_id=notebook["id"],
            filename=uploaded.name,
            data=uploaded.getvalue(),
            content_type=uploaded.type or "application/octet-stream",
        )
        st.success(f"Uploaded '{src['original_filename']}' — status: {src['ingestion_status']}.")
    except ApiError as exc:
        st.error(f"Upload failed — {exc.detail}")

st.subheader("Sources")
col1, col2 = st.columns([1, 4])
with col1:
    refresh = st.button("🔄 Refresh status")
try:
    sources = client.list_sources(notebook["id"])
except ApiError as exc:
    st.error(f"Could not load sources — {exc.detail}")
    sources = []

if not sources:
    st.info("No sources uploaded yet.")
else:
    st.dataframe(
        [
            {
                "filename": s["original_filename"],
                "type": s["source_type"],
                "status": s["ingestion_status"],
            }
            for s in sources
        ],
        use_container_width=True,
        hide_index=True,
    )
    if any(s["ingestion_status"] not in {"ready", "failed"} for s in sources):
        st.caption("Ingestion runs in the background — click Refresh to update status.")
