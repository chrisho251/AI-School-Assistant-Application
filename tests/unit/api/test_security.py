"""Unit tests for the stdlib HS256 JWT helpers."""

from __future__ import annotations

import time

import pytest

from asag.api.security import JWTError, decode_hs256, encode_hs256

_SECRET = "test-secret-key"


def test_encode_decode_roundtrip() -> None:
    claims = {"sub": "abc-123", "role": "teacher", "exp": time.time() + 60}
    token = encode_hs256(claims, _SECRET)
    decoded = decode_hs256(token, _SECRET)
    assert decoded["sub"] == "abc-123"
    assert decoded["role"] == "teacher"


def test_bad_signature_rejected() -> None:
    token = encode_hs256({"sub": "x"}, _SECRET)
    with pytest.raises(JWTError, match="signature"):
        decode_hs256(token, "wrong-secret")


def test_expired_token_rejected() -> None:
    token = encode_hs256({"sub": "x", "exp": time.time() - 1}, _SECRET)
    with pytest.raises(JWTError, match="expired"):
        decode_hs256(token, _SECRET)


def test_no_exp_is_accepted() -> None:
    # Tokens without exp are valid (signature is the only gate).
    token = encode_hs256({"sub": "x"}, _SECRET)
    assert decode_hs256(token, _SECRET)["sub"] == "x"


@pytest.mark.parametrize("bad", ["not.a.jwt.token", "onlyonepart", "two.parts"])
def test_malformed_token_rejected(bad: str) -> None:
    with pytest.raises(JWTError):
        decode_hs256(bad, _SECRET)
