"""
WebDashboard – FastAPI backend server.
Serves all data APIs consumed by the pywebview frontend.
"""
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Path bootstrap (works both dev and PyInstaller frozen) ──────────
if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from WebDashboard.api import DEFAULT_SPREADSHEET_URL, GoogleSheetsClient, validate_spreadsheet_url  # noqa: E402
from WebDashboard.data import (  # noqa: E402
    calculate_aging,
    calculate_aging_counts,
    calculate_incident_correlation,
    calculate_sla_status,
    generate_noc_report,
    generate_shift_handover,
    verify_login,
)

# ── FastAPI App ───────────────────────────────────────────────────────
app = FastAPI(title="NOC Dashboard API", version="2.0.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the static HTML/JS/CSS frontend
if getattr(sys, "frozen", False):
    STATIC_DIR = Path(sys._MEIPASS) / "WebDashboard" / "static"  # type: ignore[attr-defined]
else:
    STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── State ─────────────────────────────────────────────────────────────
_CACHE_DIR = Path.home() / ".noc_cache" / "dashboard"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_state: dict[str, Any] = {
    "spreadsheet_url": DEFAULT_SPREADSHEET_URL,
    "tickets": [],
    "loaded_at": 0.0,
    "loading": False,
    "error": None,
}

CACHE_TTL = 3 * 3600  # 3 jam


def _get_client() -> GoogleSheetsClient:
    return GoogleSheetsClient(
        spreadsheet_url=_state["spreadsheet_url"],
        cache_dir=str(_CACHE_DIR),
    )


def _load_tickets(force: bool = False) -> list[dict[str, Any]]:
    """Load tickets, with cache-first strategy."""
    if not force and _state["tickets"] and (time.time() - _state["loaded_at"]) < CACHE_TTL:
        return _state["tickets"]
    client = _get_client()
    rows = client.call("getTTData", force_refresh=force)
    _state["tickets"] = rows
    _state["loaded_at"] = time.time()
    _state["error"] = None
    return rows


# ── Auth ──────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/login")
async def login(body: LoginRequest) -> dict:
    ok, msg, name = verify_login(body.username, body.password)
    if not ok:
        raise HTTPException(status_code=401, detail=msg)
    return {"success": True, "name": name}


# ── Settings ──────────────────────────────────────────────────────────
class SettingsRequest(BaseModel):
    spreadsheet_url: str


@app.get("/api/settings")
async def get_settings() -> dict:
    return {"spreadsheet_url": _state["spreadsheet_url"]}


@app.post("/api/settings")
async def update_settings(body: SettingsRequest) -> dict:
    try:
        validated = validate_spreadsheet_url(body.spreadsheet_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _state["spreadsheet_url"] = validated
    _state["tickets"] = []  # clear cache to force reload
    _state["loaded_at"] = 0.0
    return {"success": True}


# ── Data Loading ──────────────────────────────────────────────────────
@app.get("/api/db-status")
async def db_status() -> dict:
    return {
        "loaded": bool(_state["tickets"]),
        "count": len(_state["tickets"]),
        "loaded_at": _state["loaded_at"],
        "loading": _state["loading"],
        "error": _state["error"],
    }


@app.post("/api/refresh")
async def refresh_data(force: bool = Query(default=False)) -> dict:
    """Background: load/refresh ticket data."""
    if _state["loading"]:
        return {"status": "already_loading"}
    _state["loading"] = True
    _state["error"] = None
    try:
        rows = _load_tickets(force=force)
        return {"status": "ok", "count": len(rows)}
    except Exception as e:
        _state["error"] = str(e)
        raise HTTPException(status_code=503, detail=str(e))
    finally:
        _state["loading"] = False


# ── Tickets API ───────────────────────────────────────────────────────
@app.get("/api/tickets")
async def get_tickets(
    status: str = Query(default=""),
    package: str = Query(default=""),
    province: str = Query(default=""),
    aging: str = Query(default=""),
    search: str = Query(default=""),
    limit: int = Query(default=500, le=5000),
    offset: int = Query(default=0),
) -> dict:
    tickets = _state.get("tickets", [])
    if not tickets:
        try:
            tickets = _load_tickets()
        except Exception as e:
            return {"tickets": [], "total": 0, "error": str(e)}

    now = time.time()
    filtered: list[dict] = []
    for t in tickets:
        t_status = str(t.get("status") or "").upper()
        if status and t_status != status.upper():
            continue
        if package and package != "Semua paket" and str(t.get("package") or "") != package:
            continue
        if province and province != "Semua provinsi" and str(t.get("province") or "") != province:
            continue
        if aging:
            bucket, _, _, _ = calculate_aging(t, now)
            if aging == "SLA_BREACHED":
                sla_st, _, _, _ = calculate_sla_status(t, now_ts=now)
                if sla_st not in ("BREACHED", "CRITICAL"):
                    continue
            elif aging != "ALL" and bucket != aging:
                continue
        if search:
            q = search.lower()
            if not any(
                q in str(t.get(k) or "").lower()
                for k in ("siteId", "siteName", "ticketId", "problem", "province")
            ):
                continue
        # enrich with aging info
        bucket, age_label, _, age_hours = calculate_aging(t, now)
        sla_st, sla_label, _, sla_color = calculate_sla_status(t, now_ts=now)
        filtered.append({
            **t,
            "agingBucket": bucket,
            "agingLabel": age_label,
            "agingHours": round(age_hours, 1),
            "slaStatus": sla_st,
            "slaLabel": sla_label,
            "slaColor": sla_color,
        })

    total = len(filtered)
    page = filtered[offset: offset + limit]
    return {"tickets": page, "total": total}


@app.get("/api/summary")
async def get_summary() -> dict:
    tickets = _state.get("tickets", [])
    if not tickets:
        try:
            tickets = _load_tickets()
        except Exception:
            return {}

    now = time.time()
    open_tickets = [t for t in tickets if str(t.get("status") or "").upper() == "OPEN"]
    close_tickets = [t for t in tickets if str(t.get("status") or "").upper() != "OPEN"]

    aging = calculate_aging_counts(open_tickets, now)
    sla_breached = sum(
        1 for t in open_tickets
        if calculate_sla_status(t, now_ts=now)[0] in ("BREACHED", "CRITICAL")
    )

    # Dropdown filter options
    packages = sorted({str(t.get("package") or "").strip() for t in tickets if t.get("package")})
    provinces = sorted({str(t.get("province") or "").strip() for t in tickets if t.get("province")})

    return {
        "total": len(tickets),
        "open": len(open_tickets),
        "close": len(close_tickets),
        "slaBreached": sla_breached,
        "aging": aging,
        "packages": packages,
        "provinces": provinces,
    }


@app.get("/api/trend")
async def get_trend(
    package: str = Query(default=""),
    province: str = Query(default=""),
) -> dict:
    tickets = _state.get("tickets", [])
    if not tickets:
        try:
            tickets = _load_tickets()
        except Exception:
            return {"dates": [], "counts": []}

    filtered = tickets
    if package and package != "Semua paket":
        filtered = [t for t in filtered if str(t.get("package") or "") == package]
    if province and province != "Semua provinsi":
        filtered = [t for t in filtered if str(t.get("province") or "") == province]

    date_counts: dict[str, int] = {}
    for t in filtered:
        d = str(t.get("dateQuery") or "").strip()
        if d:
            date_counts[d] = date_counts.get(d, 0) + 1

    sorted_dates = sorted(date_counts.keys())[-30:]  # last 30 days
    return {
        "dates": sorted_dates,
        "counts": [date_counts[d] for d in sorted_dates],
    }


@app.get("/api/problems")
async def get_problems(
    package: str = Query(default=""),
    province: str = Query(default=""),
    top: int = Query(default=10),
) -> dict:
    tickets = _state.get("tickets", [])
    if not tickets:
        try:
            tickets = _load_tickets()
        except Exception:
            return {"labels": [], "values": []}

    filtered = tickets
    if package and package != "Semua paket":
        filtered = [t for t in filtered if str(t.get("package") or "") == package]
    if province and province != "Semua provinsi":
        filtered = [t for t in filtered if str(t.get("province") or "") == province]

    problems: dict[str, int] = {}
    for t in filtered:
        p = str(t.get("problem") or "Other").strip()
        problems[p] = problems.get(p, 0) + 1

    top_probs = sorted(problems.items(), key=lambda kv: kv[1], reverse=True)[:top]
    labels = [p for p, _ in top_probs]
    values = [v for _, v in top_probs]
    return {"labels": labels, "values": values}


@app.get("/api/province-stats")
async def get_province_stats(
    package: str = Query(default=""),
    top: int = Query(default=8),
) -> dict:
    tickets = _state.get("tickets", [])
    if not tickets:
        try:
            tickets = _load_tickets()
        except Exception:
            return {"labels": [], "open": [], "close": []}

    filtered = tickets
    if package and package != "Semua paket":
        filtered = [t for t in filtered if str(t.get("package") or "") == package]

    prov_open: dict[str, int] = {}
    prov_close: dict[str, int] = {}
    for t in filtered:
        p = str(t.get("province") or "Unknown").strip()
        st = str(t.get("status") or "").upper()
        if st == "OPEN":
            prov_open[p] = prov_open.get(p, 0) + 1
        else:
            prov_close[p] = prov_close.get(p, 0) + 1

    all_provs = set(prov_open.keys()) | set(prov_close.keys())
    sorted_provs = sorted(all_provs, key=lambda p: (prov_open.get(p, 0) + prov_close.get(p, 0)), reverse=True)[:top]

    return {
        "labels": sorted_provs,
        "open": [prov_open.get(p, 0) for p in sorted_provs],
        "close": [prov_close.get(p, 0) for p in sorted_provs],
    }


@app.get("/api/top-closed-sites")
async def get_top_closed_sites(
    package: str = Query(default=""),
    province: str = Query(default=""),
    limit: int = Query(default=15, le=100),
) -> dict:
    tickets = _state.get("tickets", [])
    if not tickets:
        try:
            tickets = _load_tickets()
        except Exception:
            return {"sites": []}

    filtered = tickets
    if package and package != "Semua paket":
        filtered = [t for t in filtered if str(t.get("package") or "") == package]
    if province and province != "Semua provinsi":
        filtered = [t for t in filtered if str(t.get("province") or "") == province]

    closed = [t for t in filtered if str(t.get("status") or "").upper() != "OPEN"]

    site_map: dict[str, dict[str, Any]] = {}
    for t in closed:
        sid = str(t.get("siteId") or "").strip()
        if not sid:
            continue
        if sid not in site_map:
            site_map[sid] = {
                "siteId": sid,
                "siteName": str(t.get("siteName") or "-"),
                "province": str(t.get("province") or "-"),
                "package": str(t.get("package") or "-"),
                "consortium": str(t.get("consortium") or "-"),
                "closeCount": 0,
                "problems": {},
                "lastClose": "",
            }
        rec = site_map[sid]
        rec["closeCount"] += 1
        prob = str(t.get("problem") or "Other").strip()
        rec["problems"][prob] = rec["problems"].get(prob, 0) + 1
        ct = str(t.get("closeTime") or "")
        if ct and (not rec["lastClose"] or ct > rec["lastClose"]):
            rec["lastClose"] = ct

    results = []
    for sid, rec in site_map.items():
        dom_prob = max(rec["problems"].items(), key=lambda kv: kv[1])[0] if rec["problems"] else "-"
        results.append({
            "siteId": rec["siteId"],
            "siteName": rec["siteName"],
            "province": rec["province"],
            "package": rec["package"],
            "consortium": rec["consortium"],
            "closeCount": rec["closeCount"],
            "dominantProblem": dom_prob,
            "lastClose": rec["lastClose"],
        })

    results.sort(key=lambda r: r["closeCount"], reverse=True)
    return {"sites": results[:limit]}


@app.get("/api/correlation")
async def get_correlation() -> dict:
    tickets = _state.get("tickets", [])
    open_tickets = [t for t in tickets if str(t.get("status") or "").upper() == "OPEN"]
    items = calculate_incident_correlation(open_tickets)
    return {"items": items[:15]}


# ── Reporting & Handover ──────────────────────────────────────────────
@app.get("/api/reports/handover")
async def get_handover_report(
    area: str = Query(default="all"),
    pagi: str = Query(default=""),
    malam: str = Query(default=""),
    time_str: str = Query(default=""),
    include_list: bool = Query(default=False),
) -> dict:
    tickets = _state.get("tickets", [])
    report_text = generate_shift_handover(
        tickets=tickets,
        area=area,
        spreadsheet_url=_state.get("spreadsheet_url", DEFAULT_SPREADSHEET_URL),
        pagi=pagi,
        malam=malam,
        time_str=time_str,
        include_list=include_list,
    )
    return {
        "report": report_text,
        "area": area,
        "pagi": pagi,
        "malam": malam,
        "time_str": time_str,
    }


@app.get("/api/reports/noc")
async def get_noc_report_text(
    area: str = Query(default="all"),
    time_str: str = Query(default="12:00"),
    date_str: str = Query(default=""),
    include_list: bool = Query(default=False),
) -> dict:
    tickets = _state.get("tickets", [])
    report_text = generate_noc_report(
        tickets=tickets,
        area=area,
        time_str=time_str,
        date_str=date_str,
        spreadsheet_url=_state.get("spreadsheet_url", DEFAULT_SPREADSHEET_URL),
        include_list=include_list,
    )
    return {
        "report": report_text,
        "area": area,
        "time_str": time_str,
        "date_str": date_str,
    }


@app.get("/api/export-tickets")
async def export_tickets() -> StreamingResponse:
    tickets = _state.get("tickets", [])
    if not tickets:
        raise HTTPException(status_code=400, detail="Tidak ada data tiket untuk diekspor.")

    output = StringIO()
    writer = csv.writer(output)
    headers = [
        "Date Query",
        "Ticket ID",
        "Site ID",
        "Site Name",
        "Package",
        "Status",
        "Problem",
        "Duration",
        "Province",
        "Consortium",
        "Close Time",
    ]
    writer.writerow(headers)
    for t in tickets:
        writer.writerow([
            t.get("dateQuery", ""),
            t.get("ticketId", ""),
            t.get("siteId", ""),
            t.get("siteName", ""),
            t.get("package", ""),
            t.get("status", ""),
            t.get("problem", ""),
            t.get("siteDownTime", ""),
            t.get("province", ""),
            t.get("consortium", ""),
            t.get("closeTime", ""),
        ])

    output.seek(0)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"NOC_Tickets_{today}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/open-ticket-checker")
async def launch_ticket_checker() -> dict:
    # Generate a one-time launch token so WebTicketChecker/main.py passes
    # launch_guard.require_launcher_token() without showing "Akses Ditolak"
    try:
        from launch_guard import generate_launch_token  # noqa: PLC0415
        token = generate_launch_token()
    except Exception:
        token = None

    # Build the child environment with the token injected
    child_env = os.environ.copy()
    if token:
        child_env["NOC_LAUNCH_TOKEN"] = token

    # Saat frozen (EXE), sys.executable adalah path EXE Dashboard itu sendiri
    # Ticket Checker EXE biasanya ada di folder yang sama (dist/)
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else ROOT / "dist"

    candidates = [
        exe_dir / "NOC Web Ticket Checker.exe",           # folder yang sama dengan Dashboard EXE
        exe_dir.parent / "dist" / "NOC Web Ticket Checker.exe",  # fallback ke dist/ relatif
        ROOT / "dist" / "NOC Web Ticket Checker.exe",
        Path.cwd() / "dist" / "NOC Web Ticket Checker.exe",
        ROOT / "WebTicketChecker" / "main.py",
        Path.cwd() / "WebTicketChecker" / "main.py",
    ]
    for c in candidates:
        if c.exists():
            try:
                if c.suffix.lower() == ".exe":
                    subprocess.Popen(
                        [str(c)],
                        env=child_env,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    return {"success": True, "launched": str(c)}
                elif c.suffix.lower() == ".py":
                    subprocess.Popen([sys.executable, str(c)], env=child_env)
                    return {"success": True, "launched": str(c)}
            except Exception as e:
                return {"success": False, "error": str(e)}
    return {"success": False, "message": "NOC Web Ticket Checker tidak ditemukan"}


# ── Health ────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "time": time.time()}


# ── Root: serve index.html ────────────────────────────────────────────
from fastapi.responses import FileResponse  # noqa: E402


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))

