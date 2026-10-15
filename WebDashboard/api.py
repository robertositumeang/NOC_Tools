from __future__ import annotations

import csv
from io import StringIO
import json
from pathlib import Path
import re
import time
from typing import Any, Callable
from urllib.parse import urlparse
import requests

try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:
    class QThread:  # type: ignore
        def __init__(self, parent=None) -> None: pass
        def start(self) -> None: pass
    def pyqtSignal(*_args, **_kwargs):  # type: ignore
        class _Signal:
            def connect(self, *_a, **_k): pass
            def emit(self, *_a, **_k): pass
        return _Signal()

if __package__:
    from .data import normalize_performance_rows, normalize_site_rows, normalize_ticket_rows
else:
    from data import normalize_performance_rows, normalize_site_rows, normalize_ticket_rows


DEFAULT_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "10M20JUr2CiCtz3LvrmcJn8e6p4ND0UvwLqE0Z_p9HL4/edit?gid=1097310246"
)
SHEET_GIDS = {
    "getTTData": "1631492418",
    "getPerfData": "740440085",
    "getSiteManagement": "1097310246",
}
ALLOWED_ACTIONS = frozenset(SHEET_GIDS)
CACHE_TTL_SECONDS = 3 * 60 * 60  # 3 hours, matching Code.gs


def validate_spreadsheet_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    match = re.fullmatch(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})(?:/edit)?/?", parsed.path)
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != "docs.google.com"
        or match is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            "Masukkan URL Google Spreadsheet yang valid, misalnya "
            "https://docs.google.com/spreadsheets/d/ID/edit."
        )
    return url


class GoogleSheetsClient:
    def __init__(
        self,
        spreadsheet_url: str = DEFAULT_SPREADSHEET_URL,
        session: requests.Session | None = None,
        timeout_seconds: float = 60,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.spreadsheet_url = validate_spreadsheet_url(spreadsheet_url)
        match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", self.spreadsheet_url)
        if match is None:
            raise ValueError("ID Google Spreadsheet tidak ditemukan.")
        self.spreadsheet_id = match.group(1)
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.use_cache = cache_dir is not None
        if self.use_cache and cache_dir:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = None

    def _cache_path(self, key: str) -> Path | None:
        if not self.use_cache or self.cache_dir is None:
            return None
        return self.cache_dir / f"{key}_{self.spreadsheet_id}.json"

    def _get_cached_data(self, key: str) -> list[dict[str, str]] | None:
        cache_file = self._cache_path(key)
        if cache_file is None or not cache_file.exists():
            return None
        try:
            with open(cache_file, "r", encoding="utf-8") as file:
                payload = json.load(file)
            if (time.time() - payload.get("time", 0)) < CACHE_TTL_SECONDS:
                return payload.get("data")
        except Exception:
            return None
        return None

    def _save_cache(self, key: str, data: list[dict[str, str]]) -> None:
        cache_file = self._cache_path(key)
        if cache_file is None:
            return
        try:
            with open(cache_file, "w", encoding="utf-8") as file:
                json.dump({"time": time.time(), "data": data}, file)
        except Exception:
            pass

    def _read_sheet(self, gid: str, force_refresh: bool = False) -> list[dict[str, str]]:
        cache_key = f"CACHE_SHEET_{gid}"
        if not force_refresh:
            cached = self._get_cached_data(cache_key)
            if cached is not None:
                return cached


        url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/export"
        try:
            response = self.session.get(
                url,
                params={"format": "csv", "gid": gid},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(
                "Tidak dapat membaca Google Sheets. Pastikan file dibagikan "
                "sebagai Viewer kepada siapa pun yang memiliki link."
            ) from error

        final_host = (urlparse(response.url).hostname or "").lower()
        content_type = response.headers.get("Content-Type", "").lower()
        if (
            final_host != "docs.google.com"
            and not final_host.endswith(".googleusercontent.com")
        ) or "text/csv" not in content_type:
            raise RuntimeError(
                "Google Sheets tidak mengembalikan CSV publik. Ubah General "
                "access menjadi Anyone with the link — Viewer."
            )

        reader = csv.DictReader(StringIO(response.text.lstrip("\ufeff")))
        if reader.fieldnames is None:
            raise RuntimeError("Sheet kosong atau tidak memiliki baris header.")
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {
                str(key).strip(): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            if any(cleaned.values()):
                rows.append(cleaned)

        self._save_cache(cache_key, rows)
        return rows

    def call(self, action: str, force_refresh: bool = False, **_parameters: Any) -> Any:
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"Sheet Google tidak dikenal untuk operasi: {action}")
        rows = self._read_sheet(SHEET_GIDS[action], force_refresh=force_refresh)
        if action == "getTTData":
            return normalize_ticket_rows(rows)
        if action == "getPerfData":
            data, valid_dates = normalize_performance_rows(rows)
            return {"rows": data, "validDates": valid_dates}
        return normalize_site_rows(rows)


class ApiWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: GoogleSheetsClient,
        action: str,
        parameters: dict[str, Any],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.action = action
        self.parameters = parameters

    def run(self) -> None:
        try:
            result = self.client.call(self.action, **self.parameters)
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.succeeded.emit(result)


_ACTIVE_WORKERS: set[ApiWorker] = set()


def start_api_call(
    client: GoogleSheetsClient,
    action: str,
    parameters: dict[str, Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[str], None],
    parent=None,
) -> ApiWorker:
    worker = ApiWorker(client, action, parameters, parent)
    _ACTIVE_WORKERS.add(worker)

    def _cleanup() -> None:
        _ACTIVE_WORKERS.discard(worker)

    worker.succeeded.connect(on_success)
    worker.failed.connect(on_error)
    worker.succeeded.connect(_cleanup)
    worker.failed.connect(_cleanup)
    worker.start()
    return worker
