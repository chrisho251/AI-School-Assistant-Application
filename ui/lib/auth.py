"""Streamlit session auth — mints a bearer token and gates pages by role.

POC auth: the backend honours a ``dev.<user_id>.<org_id>.<role>`` token when no
JWT secret is configured (see ``api/deps.py::_parse_dev_token``), so the login form
builds one from the IDs the user pastes. A real Supabase JS handoff is the post-POC
upgrade hook — swap ``_build_dev_token`` for a token obtained from Supabase Auth.

Identity lives in ``st.session_state`` so it survives reruns within a session.
"""

from __future__ import annotations

import uuid

import streamlit as st

from lib.api import ApiClient

_TOKEN_KEY = "auth_token"
_USER_KEY = "auth_user"
_CLIENT_KEY = "auth_client"


def _build_dev_token(user_id: str, org_id: str, role: str) -> str:
    """Assemble a dev bearer token from the three identity fields."""
    return f"dev.{user_id}.{org_id}.{role}"


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def current_user() -> dict[str, str] | None:
    """Return the logged-in user's identity dict, or None if not logged in."""
    return st.session_state.get(_USER_KEY)


def get_client() -> ApiClient | None:
    """Return an ``ApiClient`` for the current session, or None if logged out.

    The client is cached in session state and reused across Streamlit reruns —
    building a fresh ``ApiClient`` per rerun would open (and never close) a new
    httpx connection pool each time, leaking sockets over a session.
    """
    token = st.session_state.get(_TOKEN_KEY)
    if not token:
        return None
    cached = st.session_state.get(_CLIENT_KEY)
    if isinstance(cached, ApiClient) and cached.token == token:
        return cached
    client = ApiClient(token)
    st.session_state[_CLIENT_KEY] = client
    return client


def logout() -> None:
    """Clear the session's identity + token, closing the cached client."""
    cached = st.session_state.pop(_CLIENT_KEY, None)
    if isinstance(cached, ApiClient):
        cached.close()
    st.session_state.pop(_TOKEN_KEY, None)
    st.session_state.pop(_USER_KEY, None)


def login_sidebar() -> dict[str, str] | None:
    """Render the login/logout widget in the sidebar; return the user if logged in.

    When logged out, shows a form to enter a user id / org id / role (POC dev login).
    When logged in, shows the identity and a logout button.
    """
    user = current_user()
    with st.sidebar:
        st.markdown("### Account")
        if user is not None:
            st.success(f"**{user['role']}**\n\n`{user['user_id']}`")
            if st.button("Log out", use_container_width=True):
                logout()
                st.rerun()
            return user

        st.caption("POC dev login — paste your seeded IDs.")
        with st.form("login"):
            role = st.selectbox("Role", ["teacher", "student"])
            user_id = st.text_input("User ID (UUID)")
            org_id = st.text_input("Org ID (UUID)")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            if not (_valid_uuid(user_id) and _valid_uuid(org_id)):
                st.error("User ID and Org ID must both be valid UUIDs.")
                return None
            st.session_state[_TOKEN_KEY] = _build_dev_token(user_id, org_id, role)
            st.session_state[_USER_KEY] = {
                "user_id": user_id,
                "org_id": org_id,
                "role": role,
            }
            st.rerun()
    return None


def require_role(role: str) -> dict[str, str]:
    """Gate a page: stop rendering unless the user is logged in with *role*.

    Returns the user identity when authorized; otherwise renders a message and
    halts the script via ``st.stop()``.
    """
    user = login_sidebar()
    if user is None:
        st.info("Please log in using the sidebar.")
        st.stop()
    if user["role"] != role:
        st.error(f"This page requires the **{role}** role. You are **{user['role']}**.")
        st.stop()
    return user
