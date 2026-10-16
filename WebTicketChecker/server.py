"""
WebTicketChecker – FastAPI backend server.
Handles DB loading, Excel file uploads, gap audit, and Excel export.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Path bootstrap (works both dev and PyInstaller frozen) ──────────
if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from WebTicketChecker.api import DEFAULT_SPREADSHEET_URL, GoogleSheetsClient, validate_spreadsheet_url  # noqa: E402
from WebTicketChecker.data import (  # noqa: E402
    audit_both_incident_files,
    extract_sheet_write_payload,
    generate_gap_csv_text,
    generate_tsv_paste_data,
    read_incident_file,
    write_gap_workbook,
)

# ── App ────────────────────────────────────────────────────────────
app = FastAPI(title="NOC Ticket Checker API", version="2.0.0", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if getattr(sys, "frozen", False):
    STATIC_DIR = Path(sys._MEIPASS) / "WebTicketChecker" / "static"  # type: ignore[attr-defined]
else:
    STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── State ──────────────────────────────────────────────────────────
_CACHE_DIR = Path.home() / ".noc_cache" / "ticket_checker"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_SETTINGS_FILE = _CACHE_DIR / "sheets_settings.json"


def _load_settings() -> dict:
    try:
        if _SETTINGS_FILE.exists():
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_settings(data: dict) -> None:
    try:
        _SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_persisted = _load_settings()

_state: dict[str, Any] = {
    "spreadsheet_url": DEFAULT_SPREADSHEET_URL,
    "apps_script_url": _persisted.get("apps_script_url", ""),
    "db_rows": [],
    "db_loaded": False,
    "db_loading": False,
    "db_error": None,
    "db_count": 0,
    "db_loaded_at": 0.0,
    "down_rows": [],
    "down_filename": "",
    "down_count": 0,
    "unmon_rows": [],
    "unmon_filename": "",
    "unmon_count": 0,
    "gaps": [],
    "summary": {},
    "checked": False,
}

CACHE_TTL = 3 * 3600


def _get_client() -> GoogleSheetsClient:
    return GoogleSheetsClient(
        spreadsheet_url=_state["spreadsheet_url"],
        cache_dir=str(_CACHE_DIR),
    )


# ── Startup: preload from cache ────────────────────────────────────
@app.on_event("startup")
async def _preload() -> None:
    """Load cached DB data on startup so UI is immediately responsive."""
    try:
        rows = await asyncio.to_thread(_get_client().get_tt_data, False)
        _state["db_rows"] = rows
        _state["db_count"] = len(rows)
        _state["db_loaded"] = True
        _state["db_loaded_at"] = time.time()
    except Exception as e:
        _state["db_error"] = str(e)


# ── Settings ───────────────────────────────────────────────────────
class SettingsBody(BaseModel):
    spreadsheet_url: str


@app.get("/api/settings")
async def get_settings() -> dict:
    return {"spreadsheet_url": _state["spreadsheet_url"]}


@app.post("/api/settings")
async def save_settings(body: SettingsBody) -> dict:
    try:
        validated = validate_spreadsheet_url(body.spreadsheet_url)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    _state["spreadsheet_url"] = validated
    _state["db_rows"] = []
    _state["db_loaded"] = False
    _state["db_count"] = 0
    return {"ok": True}


# ── DB Status ──────────────────────────────────────────────────────
@app.get("/api/db-status")
async def db_status() -> dict:
    return {
        "loaded": _state["db_loaded"],
        "loading": _state["db_loading"],
        "count": _state["db_count"],
        "loaded_at": _state["db_loaded_at"],
        "error": _state["db_error"],
        "down_count": _state["down_count"],
        "down_filename": _state["down_filename"],
        "unmon_count": _state["unmon_count"],
        "unmon_filename": _state["unmon_filename"],
        "checked": _state["checked"],
        "gap_count": len(_state["gaps"]),
    }


@app.post("/api/refresh-db")
async def refresh_db(force: bool = Query(default=False)) -> dict:
    if _state["db_loading"]:
        return {"status": "already_loading"}
    _state["db_loading"] = True
    _state["db_error"] = None
    try:
        rows = await asyncio.to_thread(_get_client().get_tt_data, force)
        _state["db_rows"] = rows
        _state["db_count"] = len(rows)
        _state["db_loaded"] = True
        _state["db_loaded_at"] = time.time()
        return {"status": "ok", "count": len(rows)}
    except Exception as e:
        _state["db_error"] = str(e)
        raise HTTPException(503, detail=str(e))
    finally:
        _state["db_loading"] = False


# ── File Upload ────────────────────────────────────────────────────
@app.post("/api/upload/{file_type}")
async def upload_file(file_type: str, files: list[UploadFile] = File(...)) -> dict:
    if file_type not in ("down", "unmon"):
        raise HTTPException(400, detail="file_type harus 'down' atau 'unmon'")

    if not files:
        raise HTTPException(400, detail="Tidak ada file yang diupload.")

    all_records: list[dict] = []
    filenames: list[str] = []

    for file in files:
        suffix = Path(file.filename or "file.xlsx").suffix.lower()
        if suffix not in (".xlsx", ".xlsm", ".xls"):
            raise HTTPException(400, detail=f"File '{file.filename}' harus berformat .xlsx, .xlsm, atau .xls")

        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            records = await asyncio.to_thread(read_incident_file, tmp_path)
            all_records.extend(records)
            filenames.append(file.filename or "")
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(422, detail=f"Gagal membaca '{file.filename}': {e}")
        finally:
            tmp_path.unlink(missing_ok=True)

    if file_type == "down":
        _state["down_rows"] = all_records
        _state["down_filename"] = ", ".join(filenames)
        _state["down_count"] = len(all_records)
    else:
        _state["unmon_rows"] = all_records
        _state["unmon_filename"] = ", ".join(filenames)
        _state["unmon_count"] = len(all_records)

    # Reset previous check result whenever files change
    _state["gaps"] = []
    _state["summary"] = {}
    _state["checked"] = False

    return {
        "ok": True,
        "count": len(all_records),
        "filename": ", ".join(filenames),
        "file_count": len(files),
    }


# ── Run Audit ──────────────────────────────────────────────────────
@app.post("/api/run-check")
async def run_check() -> dict:
    if not _state["db_loaded"]:
        raise HTTPException(400, detail="Database TT belum dimuat.")
    if not _state["down_rows"] and not _state["unmon_rows"]:
        raise HTTPException(400, detail="Belum ada file incident yang diupload.")

    def _do_audit():
        return audit_both_incident_files(
            _state["db_rows"],
            _state["down_rows"],
            _state["unmon_rows"],
        )

    try:
        gaps, summary = await asyncio.to_thread(_do_audit)
    except Exception as e:
        raise HTTPException(500, detail=str(e))

    _state["gaps"] = gaps
    _state["summary"] = summary
    _state["checked"] = True

    return {
        "summary": summary,
        "gap_count": len(gaps),
    }


# ── Gap Data ───────────────────────────────────────────────────────
@app.get("/api/gaps")
async def get_gaps(
    type: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=200, le=5000),
    offset: int = Query(default=0),
) -> dict:
    gaps = _state.get("gaps", [])

    filtered = gaps
    if type == "down":
        filtered = [g for g in gaps if g.get("type") == "down"]
    elif type == "unmon":
        filtered = [g for g in gaps if g.get("type") == "unmon"]

    if search:
        q = search.lower()
        filtered = [
            g for g in filtered
            if q in str(g.get("siteId") or "").lower()
            or q in str(g.get("siteName") or "").lower()
            or q in str(g.get("province") or "").lower()
            or q in str(g.get("dbStatus") or "").lower()
        ]

    total = len(filtered)
    page = filtered[offset: offset + limit]
    return {"gaps": page, "total": total}


def _save_to_downloads(filename: str, data: bytes) -> Path:
    dl = Path.home() / "Downloads"
    if not dl.exists():
        dl = Path.home() / "Unduhan"
    if not dl.exists():
        dl = Path.home()
    target = dl / filename
    target.write_bytes(data)
    return target


# ── Export ─────────────────────────────────────────────────────────
@app.get("/api/export")
@app.get("/api/export/xlsx")
async def export_gaps_excel() -> StreamingResponse:
    gaps = _state.get("gaps", [])
    if not gaps:
        raise HTTPException(400, detail="Tidak ada data gap untuk diekspor.")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        await asyncio.to_thread(write_gap_workbook, gaps, tmp_path)
        content = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    filename = f"NOC_Gap_Ticket_{time.strftime('%Y-%m-%d')}.xlsx"
    await asyncio.to_thread(_save_to_downloads, filename, content)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/csv")
@app.get("/api/export-csv")
async def export_gaps_csv() -> StreamingResponse:
    gaps = _state.get("gaps", [])
    if not gaps:
        raise HTTPException(400, detail="Tidak ada data gap untuk diekspor.")

    csv_text = await asyncio.to_thread(generate_gap_csv_text, gaps)
    # UTF-8 with BOM (\ufeff) so Microsoft Excel opens the CSV correctly with proper encoding and column alignment
    content = ("\ufeff" + csv_text).encode("utf-8")

    filename = f"NOC_Gap_Ticket_{time.strftime('%Y-%m-%d')}.csv"
    await asyncio.to_thread(_save_to_downloads, filename, content)
    return StreamingResponse(
        BytesIO(content),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/export-save/{fmt}")
async def export_and_save(fmt: str) -> dict:
    gaps = _state.get("gaps", [])
    if not gaps:
        raise HTTPException(400, detail="Tidak ada data gap untuk diekspor.")

    fmt_lower = fmt.lower()
    filename = f"NOC_Gap_Ticket_{time.strftime('%Y-%m-%d')}.{fmt_lower}"
    if fmt_lower == "xlsx":
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            await asyncio.to_thread(write_gap_workbook, gaps, tmp_path)
            content = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
    elif fmt_lower == "csv":
        csv_text = await asyncio.to_thread(generate_gap_csv_text, gaps)
        content = ("\ufeff" + csv_text).encode("utf-8")
    else:
        raise HTTPException(400, detail="Format harus 'xlsx' atau 'csv'")

    saved_path = await asyncio.to_thread(_save_to_downloads, filename, content)
    return {
        "ok": True,
        "filename": filename,
        "path": str(saved_path),
        "folder": str(saved_path.parent),
    }


@app.post("/api/open-downloads")
@app.get("/api/open-downloads")
async def open_downloads_folder(path: str = Query(default="")) -> dict:
    try:
        if path:
            p = Path(path)
            if p.exists() and p.is_file():
                subprocess.Popen(["explorer.exe", f"/select,{p}"])
                return {"ok": True, "path": str(p), "selected": True}
            elif p.exists():
                subprocess.Popen(["explorer.exe", str(p)])
                return {"ok": True, "path": str(p)}

        dl = Path.home() / "Downloads"
        if not dl.exists():
            dl = Path.home() / "Unduhan"
        if not dl.exists():
            dl = Path.home()

        subprocess.Popen(["explorer.exe", str(dl)])
        return {"ok": True, "path": str(dl)}
    except Exception as e:
        return {"ok": False, "error": str(e)}



# ── Google Sheets Sync Settings ────────────────────────────────────────────
class SheetsSettingsBody(BaseModel):
    apps_script_url: str


@app.get("/api/sheets-settings")
async def get_sheets_settings() -> dict:
    return {"apps_script_url": _state.get("apps_script_url", "")}


@app.post("/api/sheets-settings")
async def save_sheets_settings(body: SheetsSettingsBody) -> dict:
    url = body.apps_script_url.strip()
    # Validasi minimal: URL harus mengandung script.google.com atau kosong
    if url and "script.google.com" not in url:
        raise HTTPException(400, detail="URL harus berupa Apps Script Web App URL (script.google.com/...)")
    _state["apps_script_url"] = url
    _save_settings({"apps_script_url": url})
    return {"ok": True}


# ── Write to Google Sheets ─────────────────────────────────────────────────
class WriteToSheetsBody(BaseModel):
    indices: list[int]


@app.post("/api/write-to-sheets")
async def write_to_sheets(body: WriteToSheetsBody) -> dict:
    gaps = _state.get("gaps", [])
    if not gaps:
        raise HTTPException(400, detail="Belum ada data gap. Jalankan pengecekan terlebih dahulu.")

    indices = body.indices
    if not indices:
        raise HTTPException(400, detail="Tidak ada baris yang dipilih.")

    # Ekstrak payload
    payload = await asyncio.to_thread(extract_sheet_write_payload, gaps, indices)
    if not payload:
        raise HTTPException(400, detail="Tidak ada data valid untuk ditulis.")

    apps_script_url = _state.get("apps_script_url", "").strip()

    if apps_script_url:
        # Kirim ke Apps Script Web App
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    apps_script_url,
                    json={"rows": payload},
                    headers={"Content-Type": "application/json"},
                    follow_redirects=True,
                )
                if resp.status_code >= 400:
                    raise HTTPException(
                        502,
                        detail=f"Apps Script mengembalikan error: HTTP {resp.status_code} — {resp.text[:300]}"
                    )
                # Cek respons dari Apps Script
                try:
                    result = resp.json()
                except Exception:
                    result = {"message": resp.text}

                return {
                    "ok": True,
                    "mode": "apps_script",
                    "rows_written": len(payload),
                    "apps_script_response": result,
                }
        except httpx.TimeoutException:
            raise HTTPException(504, detail="Timeout saat menghubungi Apps Script. Coba lagi atau gunakan mode Salin TSV.")
        except httpx.RequestError as e:
            raise HTTPException(502, detail=f"Gagal menghubungi Apps Script: {str(e)}")
    else:
        # Kembalikan payload saja (mode TSV / manual)
        raise HTTPException(
            400,
            detail="Apps Script URL belum dikonfigurasi. Gunakan tombol 'Salin Siap Paste' atau konfigurasikan URL terlebih dahulu."
        )


@app.post("/api/generate-tsv")
async def generate_tsv(body: WriteToSheetsBody) -> dict:
    """Generate TSV string untuk clipboard paste ke Google Sheets."""
    gaps = _state.get("gaps", [])
    if not gaps:
        raise HTTPException(400, detail="Belum ada data gap.")

    indices = body.indices
    if not indices:
        raise HTTPException(400, detail="Tidak ada baris yang dipilih.")

    tsv = await asyncio.to_thread(generate_tsv_paste_data, gaps, indices)
    payload = await asyncio.to_thread(extract_sheet_write_payload, gaps, indices)
    return {
        "ok": True,
        "tsv": tsv,
        "rows": len(payload),
        "columns": [
            "Site ID (C)", "Alarm ID (M)", "Alarm Title (N)", "Ticket ID (O)",
            "Ticket Duration (P)", "State Condition (Q)", "Date Time Site Down (S)",
            "Status (X)", "Administrative State 1 (Y)", "Administrative State 2 (Z)",
            "Operation State (AA)",
        ],
    }


# ── Health ──────────────────────────────────────────────────────────
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "time": time.time()}


# ── Root ────────────────────────────────────────────────────────────
@app.get("/")
async def root() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))

