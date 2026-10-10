"""
Unit tests for NOC Tools Authentication & Cryptography.
PT. Lindu Putra Utama | Anti-Slop Security Test Suite
"""
from __future__ import annotations

import time
import pytest

from auth import (
    verify_credentials,
    make_session_token,
    verify_session_token,
    _double_crypt_hash,
)


def test_valid_user1_papua():
    is_valid, user_label = verify_credentials("NOC_Papua", "ButuhAksesLogin#2026")
    assert is_valid is True
    assert user_label == "NOC Papua"


def test_valid_user2_maluku():
    is_valid, user_label = verify_credentials("NOC_Maluku", "JanganKasihTau@2026")
    assert is_valid is True
    assert user_label == "NOC Maluku"


def test_invalid_password():
    is_valid, user_label = verify_credentials("NOC_Papua", "WrongPassword123!")
    assert is_valid is False
    assert user_label == ""


def test_invalid_username():
    is_valid, user_label = verify_credentials("Admin_Papua", "ButuhAksesLogin#2026")
    assert is_valid is False
    assert user_label == ""


def test_empty_or_whitespace():
    assert verify_credentials("", "") == (False, "")
    assert verify_credentials("   ", "   ") == (False, "")
    assert verify_credentials("NOC_Papua", "") == (False, "")
    assert verify_credentials("", "ButuhAksesLogin#2026") == (False, "")


def test_case_sensitivity():
    # Passwords and usernames must be strictly case-sensitive
    assert verify_credentials("noc_papua", "ButuhAksesLogin#2026") == (False, "")
    assert verify_credentials("NOC_Papua", "butuhakseslogin#2026") == (False, "")
    assert verify_credentials("noc_maluku", "JanganKasihTau@2026") == (False, "")


def test_session_token_lifecycle():
    token = make_session_token("NOC_Papua")
    assert isinstance(token, str)
    assert len(token.split(":")) == 3

    valid, user = verify_session_token(token)
    assert valid is True
    assert user == "NOC_Papua"


def test_session_token_tampering():
    token = make_session_token("NOC_Papua")
    parts = token.split(":")
    # Tamper with username
    tampered = f"NOC_Maluku:{parts[1]}:{parts[2]}"
    valid, user = verify_session_token(tampered)
    assert valid is False
    assert user == ""


def test_session_token_expiration():
    # Generate token with artificial timestamp 200 seconds ago
    old_ts = str(int(time.time()) - 200)
    import hmac
    import hashlib
    from auth import _HMAC_PEPPER

    payload = f"NOC_Papua:{old_ts}".encode("utf-8")
    sig = hmac.new(_HMAC_PEPPER, payload, hashlib.sha256).hexdigest()
    expired_token = f"NOC_Papua:{old_ts}:{sig}"

    valid, user = verify_session_token(expired_token, max_age_seconds=60)
    assert valid is False
    assert user == ""


def test_no_plaintext_passwords_in_source():
    from pathlib import Path
    source_code = (Path(__file__).parent / "auth.py").read_text(encoding="utf-8")
    # Neither password should appear in plain text inside auth.py
    assert "ButuhAksesLogin#2026" not in source_code
    assert "JanganKasihTau@2026" not in source_code

