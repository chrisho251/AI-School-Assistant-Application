"""Minimal HS256 JWT encode/decode — verifies Supabase access tokens without PyJWT.

Supabase signs access tokens with the project JWT secret (HS256). This module
implements just enough of JWS (sign + verify + exp check) using the stdlib so the
API edge can authenticate without pulling in a new dependency.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class JWTError(Exception):
    """Raised when a token is malformed, has a bad signature, or is expired."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    # JWT strips base64 padding; restore it before decoding.
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def encode_hs256(payload: dict[str, Any], secret: str) -> str:
    """Sign *payload* into a compact HS256 JWT. Used by tests and the dev login handoff."""
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_hs256(token: str, secret: str) -> dict[str, Any]:
    """Verify an HS256 JWT and return its claims.

    Raises:
        JWTError: malformed token, signature mismatch, or past ``exp``.
    """
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise JWTError("token is not a well-formed JWT") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    # compare_digest guards against timing side-channels on signature comparison.
    if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
        raise JWTError("signature verification failed")

    try:
        claims: dict[str, Any] = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise JWTError("token payload is not valid JSON") from exc

    exp = claims.get("exp")
    if exp is not None and time.time() > float(exp):
        raise JWTError("token has expired")
    return claims
