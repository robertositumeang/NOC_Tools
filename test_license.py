"""
Unit tests for NOC Tools Encrypted License Management & Verification.
PT. Lindu Putra Utama | Enterprise Security Suite
"""
from __future__ import annotations

import time
import pytest

from license_mgr import (
    get_machine_id,
    verify_license_key,
    save_license,
    load_installed_license,
)
from admin_license_tool import encrypt_license_key


def test_machine_id_format():
    mid = get_machine_id()
    assert isinstance(mid, str)
    assert mid.startswith("NOC-")
    parts = mid.split("-")
    assert len(parts) == 5
    for p in parts[1:]:
        assert len(p) == 4
        assert p.isalnum()


def test_license_1_month_generate_and_verify():
    mid = get_machine_id()
    key = encrypt_license_key(mid, days_valid=30, operator="NOC_Papua", license_type="1_MONTH")
    assert key.startswith("NOC-LIC1M-")

    valid, msg, days_left, exp_date = verify_license_key(key)
    assert valid is True
    assert "Aktif" in msg
    assert days_left in (29, 30)
    assert exp_date != ""


def test_license_machine_binding_mismatch():
    fake_mid = "NOC-AAAA-BBBB-CCCC-DDDD"
    key = encrypt_license_key(fake_mid, days_valid=30)

    valid, msg, days_left, exp_date = verify_license_key(key)
    assert valid is False
    assert "terikat ke perangkat lain" in msg


def test_license_tampered_encrypted_payload():
    mid = get_machine_id()
    key = encrypt_license_key(mid, days_valid=30)
    # Alter ciphertext character
    tampered = key[:-2] + ("A" if key[-2] != "A" else "B") + key[-1]

    valid, msg, days_left, exp_date = verify_license_key(tampered)
    assert valid is False


def test_license_expired():
    mid = get_machine_id()
    key = encrypt_license_key(mid, days_valid=-5)

    valid, msg, days_left, exp_date = verify_license_key(key)
    assert valid is False
    assert "telah habis" in msg


def test_license_save_and_load(tmp_path, monkeypatch):
    test_lic_file = tmp_path / "license.lic"
    test_dir = tmp_path
    monkeypatch.setattr("license_mgr._STORAGE_DIR", test_dir)
    monkeypatch.setattr("license_mgr._LICENSE_FILE", test_lic_file)

    sample_key = "NOC-LIC1M-TEST-12345"
    assert save_license(sample_key) is True
    assert load_installed_license() == sample_key
