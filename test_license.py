"""Tests for Ed25519-signed, machine-bound license verification."""
from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import license_mgr
import license_server
from license_issuer import create_signing_keypair, encrypt_license_key
from license_crypto import LEGACY_LICENSE_PREFIX, encode_signed_payload
from license_mgr import (
    get_machine_id,
    load_installed_license,
    save_license,
    verify_license_key,
)


def _write_signing_key(path):
    private_key = Ed25519PrivateKey.generate()
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return public_key


def _license_key(
    private_key_path,
    machine_id,
    days=30,
    email="user@example.com",
):
    return encrypt_license_key(
        machine_id,
        email=email,
        days_valid=days,
        operator="NOC_Operator",
        private_key_path=private_key_path,
    )


def test_machine_id_format():
    machine_id = get_machine_id()
    assert isinstance(machine_id, str)
    assert machine_id.startswith("NOC-")
    parts = machine_id.split("-")
    assert len(parts) == 5
    assert all(len(part) == 4 and part.isalnum() for part in parts[1:])


def test_signed_license_verifies_and_is_bound_to_machine(tmp_path, monkeypatch):
    key_path = tmp_path / "signing.pem"
    public_key = _write_signing_key(key_path)
    monkeypatch.setattr(license_mgr, "_LICENSE_PUBLIC_KEY", public_key)
    monkeypatch.setattr(license_server, "LICENSE_PUBLIC_KEY", public_key)

    key = _license_key(key_path, get_machine_id())
    database_path = tmp_path / "activations.sqlite3"
    license_server.initialize_database(database_path)
    assert key.startswith("NOC-LIC3-")
    activation_token = license_server.activate_license(
        "user@example.com",
        key,
        get_machine_id(),
        database_path=database_path,
        private_key_path=key_path,
    )
    valid, message, days_left, expiry_date = verify_license_key(activation_token)
    assert valid is True
    assert "Aktif" in message
    assert days_left in (29, 30)
    assert expiry_date


def test_license_signature_detects_payload_tampering(tmp_path, monkeypatch):
    key_path = tmp_path / "signing.pem"
    public_key = _write_signing_key(key_path)
    monkeypatch.setattr(license_mgr, "_LICENSE_PUBLIC_KEY", public_key)
    key = _license_key(key_path, get_machine_id())
    first_payload_character = len("NOC-LIC3-")
    replacement = "A" if key[first_payload_character] != "A" else "B"

    tampered_key = (
        key[:first_payload_character]
        + replacement
        + key[first_payload_character + 1:]
    )
    try:
        license_mgr._verify_issued_license(
            "user@example.com",
            get_machine_id(),
            tampered_key,
        )
    except ValueError as error:
        assert "Tanda tangan digital" in str(error)
    else:
        raise AssertionError("Tampered license was accepted.")


def test_license_is_bound_to_target_machine(tmp_path, monkeypatch):
    key_path = tmp_path / "signing.pem"
    public_key = _write_signing_key(key_path)
    monkeypatch.setattr(license_mgr, "_LICENSE_PUBLIC_KEY", public_key)
    key = _license_key(key_path, "NOC-AAAA-BBBB-CCCC-DDDD")
    monkeypatch.setattr(license_mgr, "get_machine_id", lambda: "NOC-EEEE-FFFF-GGGG-HHHH")

    try:
        license_mgr._verify_issued_license(
            "user@example.com",
            "NOC-EEEE-FFFF-GGGG-HHHH",
            key,
        )
    except ValueError as error:
        assert "tidak cocok" in str(error)
    else:
        raise AssertionError("License for a different machine was accepted.")


def test_expired_signed_license_is_rejected(tmp_path, monkeypatch):
    key_path = tmp_path / "signing.pem"
    public_key = _write_signing_key(key_path)
    monkeypatch.setattr(license_mgr, "_LICENSE_PUBLIC_KEY", public_key)
    monkeypatch.setattr(license_server, "LICENSE_PUBLIC_KEY", public_key)
    key = _license_key(key_path, get_machine_id())
    database_path = tmp_path / "activations.sqlite3"
    license_server.initialize_database(database_path)
    activation_token = license_server.activate_license(
        "user@example.com",
        key,
        get_machine_id(),
        database_path=database_path,
        private_key_path=key_path,
    )
    monkeypatch.setattr(license_mgr.time, "time", lambda: 2_000_000_000)
    monkeypatch.setattr(license_mgr, "_read_last_seen_time", lambda: 0)
    monkeypatch.setattr(license_mgr, "_record_seen_time", lambda timestamp: None)

    valid, message, days_left, expiry_date = verify_license_key(activation_token)
    assert valid is False
    assert "telah habis" in message
    assert days_left == 0
    assert expiry_date


def test_legacy_license_formats_are_rejected(tmp_path):
    valid, message, days_left, expiry_date = verify_license_key("NOC-LIC1M-ABCD")
    assert valid is False
    assert "diterbitkan ulang" in message
    assert days_left == 0
    assert expiry_date == ""


def test_v2_signed_license_remains_supported_until_expiry(tmp_path, monkeypatch):
    key_path = tmp_path / "signing.pem"
    public_key = _write_signing_key(key_path)
    monkeypatch.setattr(license_mgr, "_LICENSE_PUBLIC_KEY", public_key)
    private_key = serialization.load_pem_private_key(
        key_path.read_bytes(),
        password=None,
    )
    issued_at = int(license_mgr.time.time())
    key = encode_signed_payload(
        {
            "v": 2,
            "mid": get_machine_id(),
            "iat": issued_at,
            "exp": issued_at + 86400,
            "type": "1_DAY",
            "op": "legacy",
        },
        private_key,
        LEGACY_LICENSE_PREFIX,
    )
    valid, _, days_left, _ = verify_license_key(key)
    assert valid is True
    assert days_left in (0, 1)


def test_license_duration_must_be_positive(tmp_path):
    key_path = tmp_path / "signing.pem"
    _write_signing_key(key_path)
    try:
        _license_key(key_path, get_machine_id(), days=0)
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("Non-positive license duration was accepted.")


def test_signing_key_generation_refuses_to_overwrite(tmp_path):
    key_path = tmp_path / "private.pem"
    public_key = create_signing_keypair(key_path)
    assert len(public_key) == 32
    assert key_path.is_file()
    try:
        create_signing_keypair(key_path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Existing private key was overwritten.")


def test_license_save_and_load(tmp_path, monkeypatch):
    test_license_file = tmp_path / "license.lic"
    monkeypatch.setattr(license_mgr, "_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(license_mgr, "_LICENSE_FILE", test_license_file)

    sample_key = "NOC-ACT1-test"
    assert save_license(sample_key) is True
    assert load_installed_license() == sample_key
