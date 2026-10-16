"""Unit tests for the Cloudflare Worker HTTP client."""
from __future__ import annotations

import requests
import pytest

import cloudflare_api
from cloudflare_api import NocAdminApi, WorkerApiError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.mark.parametrize(
    "url",
    [
        "http://example.workers.dev",
        "https://",
        "https://user:password@example.workers.dev",
        "https://example.workers.dev/path?query=value",
        "https://example.workers.dev/#fragment",
    ],
)
def test_base_url_rejects_non_https_or_ambiguous_urls(url):
    with pytest.raises(WorkerApiError):
        cloudflare_api._base_url(url)


def test_base_url_uses_official_default_and_honors_environment_override(monkeypatch):
    monkeypatch.delenv("NOC_LICENSE_API_URL", raising=False)
    assert (
        cloudflare_api._base_url()
        == "https://noc-license-api.pasitumeangroberto.workers.dev"
    )

    monkeypatch.setenv("NOC_LICENSE_API_URL", "https://custom.example.com/")
    assert cloudflare_api._base_url() == "https://custom.example.com"
    assert (
        cloudflare_api._base_url("https://explicit.example.com/")
        == "https://explicit.example.com"
    )


def test_request_json_sends_verified_https_request_and_bearer_token(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return FakeResponse({"ok": True})

    monkeypatch.setattr(cloudflare_api.requests, "request", fake_request)

    result = cloudflare_api.request_json(
        "/v1/admin/users",
        method="GET",
        token="secret-token",
        api_url="https://example.workers.dev/",
    )

    assert result == {"ok": True}
    assert captured["method"] == "GET"
    assert captured["url"] == "https://example.workers.dev/v1/admin/users"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["timeout"] == (5, 15)
    assert captured["verify"] is True


def test_request_json_translates_network_and_invalid_response_failures(monkeypatch):
    def network_failure(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(cloudflare_api.requests, "request", network_failure)
    with pytest.raises(WorkerApiError, match="Tidak dapat menghubungi"):
        cloudflare_api.request_json(
            "/v1/login",
            api_url="https://example.workers.dev",
        )

    monkeypatch.setattr(
        cloudflare_api.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(ValueError("not JSON")),
    )
    with pytest.raises(WorkerApiError, match="Respons Cloudflare Worker tidak valid"):
        cloudflare_api.request_json(
            "/v1/login",
            api_url="https://example.workers.dev",
        )


def test_operator_login_distinguishes_wrong_password_from_service_failure(monkeypatch):
    monkeypatch.setattr(
        cloudflare_api,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WorkerApiError("Username atau kata sandi tidak valid.")
        ),
    )
    assert cloudflare_api.operator_login("operator", "wrong") == (False, "")

    monkeypatch.setattr(
        cloudflare_api,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WorkerApiError("Tidak dapat menghubungi Cloudflare Worker.")
        ),
    )
    with pytest.raises(WorkerApiError, match="Tidak dapat menghubungi"):
        cloudflare_api.operator_login("operator", "password")


def test_admin_client_bootstraps_authenticates_and_manages_records(monkeypatch):
    calls = []
    responses = [
        {"bootstrap_required": True},
        {"created": True},
        {"token": "admin-session"},
        {"users": [{"username": "operator"}]},
        {"created": True},
        {"updated": True},
        {"updated": True},
        {"license_key": "NOC-LIC3-signed"},
        {"licenses": [{"email": "operator@example.com"}]},
        {"logged_out": True},
    ]

    def fake_request_json(path, **kwargs):
        calls.append((path, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(cloudflare_api, "request_json", fake_request_json)
    api = NocAdminApi("https://example.workers.dev")

    assert api.bootstrap_status() is True
    api.bootstrap("setup-secret", "admin", "Administrator", "StrongAdminPassword!2026")
    api.login("admin", "StrongAdminPassword!2026")
    assert api.is_authenticated is True
    assert api.list_users() == [{"username": "operator"}]
    api.create_user("operator", "NOC Operator", "StrongOperatorPassword!2026")
    api.reset_password("operator", "ReplacementPassword!2026")
    api.set_user_active("operator", False)
    assert (
        api.issue_license(
            "operator@example.com",
            "NOC-AAAA-BBBB-CCCC-DDDD",
            30,
            "NOC_Operator",
        )
        == "NOC-LIC3-signed"
    )
    assert api.list_licenses() == [{"email": "operator@example.com"}]
    api.logout()
    assert api.is_authenticated is False

    assert [call[0] for call in calls] == [
        "/v1/admin/status",
        "/v1/admin/bootstrap",
        "/v1/admin/login",
        "/v1/admin/users",
        "/v1/admin/users",
        "/v1/admin/users/password",
        "/v1/admin/users/status",
        "/v1/admin/licenses/issue",
        "/v1/admin/licenses",
        "/v1/admin/logout",
    ]
    assert calls[3][1]["token"] == "admin-session"
    assert calls[7][1]["payload"] == {
        "email": "operator@example.com",
        "machine_id": "NOC-AAAA-BBBB-CCCC-DDDD",
        "days": 30,
        "operator": "NOC_Operator",
    }


def test_admin_client_deletes_expired_licenses_and_validates_counts(monkeypatch):
    calls = []
    api = NocAdminApi("https://example.workers.dev")
    api._token = "admin-session"

    def fake_request_json(path, **kwargs):
        calls.append((path, kwargs))
        return {"deleted_licenses": 2, "cleared_activations": 1}

    monkeypatch.setattr(cloudflare_api, "request_json", fake_request_json)

    assert api.delete_expired_licenses() == {
        "deleted_licenses": 2,
        "cleared_activations": 1,
    }
    assert calls == [
        (
            "/v1/admin/licenses/expired",
            {
                "method": "DELETE",
                "payload": None,
                "token": "admin-session",
                "api_url": "https://example.workers.dev",
            },
        )
    ]

    monkeypatch.setattr(
        cloudflare_api,
        "request_json",
        lambda *args, **kwargs: {
            "deleted_licenses": True,
            "cleared_activations": 0,
        },
    )
    with pytest.raises(WorkerApiError, match="Respons penghapusan lisensi"):
        api.delete_expired_licenses()


@pytest.mark.parametrize(
    "response",
    [
        {"deleted_licenses": -1, "cleared_activations": 0},
        {"deleted_licenses": 0, "cleared_activations": -1},
        {"deleted_licenses": "1", "cleared_activations": 0},
        {"deleted_licenses": 0},
        {"deleted_licenses": 0, "cleared_activations": None},
    ],
)
def test_admin_client_rejects_invalid_expired_license_cleanup_counts(
    monkeypatch, response
):
    api = NocAdminApi("https://example.workers.dev")
    api._token = "admin-session"
    monkeypatch.setattr(
        cloudflare_api,
        "request_json",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(WorkerApiError, match="Respons penghapusan lisensi"):
        api.delete_expired_licenses()
