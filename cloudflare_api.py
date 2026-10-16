"""HTTPS client for the NOC Tools Cloudflare Worker API."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from service_config import DEFAULT_LICENSE_API_URL, LICENSE_API_URL_ENV


class WorkerApiError(ValueError):
    """A safe, user-displayable Cloudflare Worker API failure."""


def _base_url(api_url: str | None = None) -> str:
    value = (
        api_url
        or os.environ.get(LICENSE_API_URL_ENV, "")
        or DEFAULT_LICENSE_API_URL
    ).strip()
    if not value:
        raise WorkerApiError(
            "URL Cloudflare Worker belum dikonfigurasi "
            f"(variabel lingkungan {LICENSE_API_URL_ENV})."
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise WorkerApiError("URL Cloudflare Worker harus menggunakan HTTPS yang valid.")
    return urlunsplit(("https", parsed.netloc, parsed.path.rstrip("/"), "", ""))


def request_json(
    path: str,
    *,
    method: str = "POST",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    api_url: str | None = None,
) -> dict[str, Any]:
    if not path.startswith("/v1/"):
        raise ValueError("Worker API path must start with /v1/.")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(
            method,
            f"{_base_url(api_url)}{path}",
            json=payload,
            headers=headers,
            timeout=(5, 15),
            verify=True,
        )
    except requests.RequestException as exc:
        raise WorkerApiError(f"Tidak dapat menghubungi Cloudflare Worker: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise WorkerApiError(
            f"Respons Cloudflare Worker tidak valid (HTTP {response.status_code})."
        ) from exc
    if not isinstance(data, dict):
        raise WorkerApiError(
            f"Respons Cloudflare Worker tidak valid (HTTP {response.status_code})."
        )
    if not response.ok:
        detail = data.get("detail")
        if not isinstance(detail, str) or not detail:
            detail = f"Cloudflare Worker menolak permintaan (HTTP {response.status_code})."
        raise WorkerApiError(detail)
    return data


def operator_login(
    username: str,
    password: str,
    *,
    api_url: str | None = None,
) -> tuple[bool, str]:
    try:
        result = request_json(
            "/v1/login",
            payload={"username": username, "password": password},
            api_url=api_url,
        )
    except WorkerApiError as exc:
        if str(exc) == "Username atau kata sandi tidak valid.":
            return False, ""
        raise
    authenticated = result.get("authenticated")
    display_name = result.get("display_name")
    if authenticated is not True or not isinstance(display_name, str) or not display_name:
        raise WorkerApiError("Respons login Cloudflare Worker tidak valid.")
    return True, display_name


class NocAdminApi:
    """In-memory administrator session client; tokens are never persisted."""

    def __init__(self, api_url: str | None = None) -> None:
        self.api_url = _base_url(api_url)
        self._token: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    def bootstrap_status(self) -> bool:
        result = request_json(
            "/v1/admin/status",
            method="GET",
            api_url=self.api_url,
        )
        value = result.get("bootstrap_required")
        if not isinstance(value, bool):
            raise WorkerApiError("Status setup administrator tidak valid.")
        return value

    def bootstrap(
        self,
        bootstrap_secret: str,
        username: str,
        display_name: str,
        password: str,
    ) -> None:
        request_json(
            "/v1/admin/bootstrap",
            payload={
                "bootstrap_secret": bootstrap_secret,
                "username": username,
                "display_name": display_name,
                "password": password,
            },
            api_url=self.api_url,
        )

    def login(self, username: str, password: str) -> None:
        result = request_json(
            "/v1/admin/login",
            payload={"username": username, "password": password},
            api_url=self.api_url,
        )
        token = result.get("token")
        if not isinstance(token, str) or not token:
            raise WorkerApiError("Respons login administrator tidak valid.")
        self._token = token

    def logout(self) -> None:
        if self._token:
            try:
                request_json(
                    "/v1/admin/logout",
                    token=self._token,
                    api_url=self.api_url,
                )
            finally:
                self._token = None

    def _request(
        self,
        path: str,
        *,
        method: str = "POST",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            raise WorkerApiError("Login administrator diperlukan.")
        return request_json(
            path,
            method=method,
            payload=payload,
            token=self._token,
            api_url=self.api_url,
        )

    def list_users(self) -> list[dict[str, Any]]:
        result = self._request("/v1/admin/users", method="GET")
        users = result.get("users")
        if not isinstance(users, list) or any(not isinstance(user, dict) for user in users):
            raise WorkerApiError("Daftar akun dari Cloudflare Worker tidak valid.")
        return users

    def create_user(
        self,
        username: str,
        display_name: str,
        password: str,
        *,
        role: str = "operator",
    ) -> None:
        self._request(
            "/v1/admin/users",
            payload={
                "username": username,
                "display_name": display_name,
                "password": password,
                "role": role,
            },
        )

    def reset_password(self, username: str, password: str) -> None:
        self._request(
            "/v1/admin/users/password",
            payload={"username": username, "password": password},
        )

    def set_user_active(self, username: str, active: bool) -> None:
        self._request(
            "/v1/admin/users/status",
            payload={"username": username, "active": active},
        )

    def issue_license(
        self,
        email: str,
        machine_id: str,
        days: int,
        operator: str,
    ) -> str:
        result = self._request(
            "/v1/admin/licenses/issue",
            payload={
                "email": email,
                "machine_id": machine_id,
                "days": days,
                "operator": operator,
            },
        )
        license_key = result.get("license_key")
        if not isinstance(license_key, str) or not license_key.startswith("NOC-LIC3-"):
            raise WorkerApiError("Respons penerbitan lisensi tidak valid.")
        return license_key

    def list_licenses(self) -> list[dict[str, Any]]:
        result = self._request("/v1/admin/licenses", method="GET")
        licenses = result.get("licenses")
        if not isinstance(licenses, list) or any(
            not isinstance(license_item, dict) for license_item in licenses
        ):
            raise WorkerApiError("Daftar lisensi dari Cloudflare Worker tidak valid.")
        return licenses

    def delete_expired_licenses(self) -> dict[str, int]:
        result = self._request(
            "/v1/admin/licenses/expired",
            method="DELETE",
        )
        return self._license_deletion_counts(result)

    def delete_licenses_by_email(self, emails: list[str]) -> dict[str, int]:
        result = self._request(
            "/v1/admin/licenses/by-email",
            method="DELETE",
            payload={"emails": emails},
        )
        return self._license_deletion_counts(result)

    @staticmethod
    def _license_deletion_counts(result: dict[str, Any]) -> dict[str, int]:
        deleted_licenses = result.get("deleted_licenses")
        cleared_activations = result.get("cleared_activations")
        if (
            type(deleted_licenses) is not int
            or deleted_licenses < 0
            or type(cleared_activations) is not int
            or cleared_activations < 0
        ):
            raise WorkerApiError("Respons penghapusan lisensi tidak valid.")
        return {
            "deleted_licenses": deleted_licenses,
            "cleared_activations": cleared_activations,
        }
