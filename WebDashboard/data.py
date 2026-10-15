from __future__ import annotations

from datetime import date, datetime
import hashlib
from pathlib import Path
import re
import time
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
import xlrd


# ── Credential Store (Matching Code.gs SHA-256) ────────────────────────
AUTH_USERS = {
    "NOC_Papua": {
        "hash": "24492d18db8e31692825495df5bc871f08ddb32b4537935889f3d394317bd2aa",
        "name": "NOC Papua",
    },
    "NOC_Maluku": {
        "hash": "5e377a46fa256dd9c3d166d29148007d59abad5d6514b676760b8fb7bae8904d",
        "name": "NOC Maluku",
    },
}

PKG_MAP = {
    "10": "10 - Maluku",
    "11": "11 - Papua Barat",
}
ALIAS_MAP = {
    "10": "AREA 5 - MALUKU",
    "10 - maluku": "AREA 5 - MALUKU",
    "11": "AREA 6 - PAPUA BARAT",
    "11 - papua barat": "AREA 6 - PAPUA BARAT",
}


def hash_password(str_val: str) -> str:
    return hashlib.sha256(str_val.strip().encode("utf-8")).hexdigest()


def verify_login(username: str, password: str) -> tuple[bool, str, str]:
    u = username.strip()
    user = AUTH_USERS.get(u)
    if not user:
        return False, "Username atau password salah!", ""
    if user["hash"] != hash_password(password):
        return False, "Username atau password salah!", ""
    return True, "Login berhasil", user["name"]


# ── Normalization Helpers ──────────────────────────────────────────────
def normalize_column_name(value: Any) -> str:
    return re.sub(r"[\s_\-/]+", "", str(value or "").strip()).casefold()


def get_column_value(row: dict[str, Any], candidates: Iterable[str]) -> str:
    normalized = {normalize_column_name(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalized.get(normalize_column_name(candidate))
        if value is not None and value != "":
            return str(value).strip()
    return ""


def _raw_column(row: dict[str, Any], candidates: Iterable[str]) -> str:
    return get_column_value(row, candidates)


def _percent(value: Any) -> float | None:
    if value is None:
        return None
    normalized = str(value).strip().replace("%", "")
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(",", "")
    else:
        normalized = normalized.replace(",", ".")
    if not normalized:
        return None
    try:
        result = float(normalized)
    except ValueError:
        return None
    if 0 <= result <= 1:
        result *= 100
    return result


def _parse_timestamp(value: Any) -> float:
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def norm_pkg(val: str) -> str:
    k = val.lower().strip()
    return ALIAS_MAP.get(k) or PKG_MAP.get(val) or val or "Unknown"


# ── Data Normalization ────────────────────────────────────────────────
def normalize_ticket_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        site_id = _raw_column(row, ("Site ID", "SiteID", "id"))
        if not site_id:
            continue
        down_time_raw = _raw_column(
            row, ("Date Time Site Down", "Down Time", "Occur Time", "Occure Time")
        )
        down_ts = _parse_timestamp(down_time_raw)
        duration_raw = _raw_column(
            row, ("Site Down Duration", "Ticket Duration", "Duration")
        )
        normalized.append(
            {
                **row,
                "dateQuery": _raw_column(row, ("Date Query", "Date", "Tanggal")),
                "ticketId": _raw_column(row, ("Ticket ID", "TT Number", "TicketID")),
                "siteId": site_id,
                "siteName": _raw_column(row, ("Site Name", "SiteName", "Name")),
                "package": _raw_column(row, ("Opsel Area Package", "Package", "Paket")),
                "status": _raw_column(row, ("Status TT", "Status")).upper(),
                "problem": _raw_column(
                    row, ("Problem", "Alarm Title", "Sub Problem", "Problem Detail")
                ),
                "siteDownTime": duration_raw or down_time_raw,
                "siteDownTimestamp": down_ts,
                "dateTimeSiteDown": down_time_raw,
                "closeTime": _raw_column(row, ("Close Time", "Clear Time")),
                "consortium": _raw_column(row, ("Consortium", "Konsorsium Pembangunan", "Konsorsium")),
                "province": _raw_column(row, ("Province", "Provinsi", "Provinsi Lama")),
                "regency": _raw_column(row, ("Regency/City", "Kab/Kota", "Kabupaten")),
                "statusBAPL": _raw_column(row, ("Status BAPL", "BAPL")),
                "spmsStatus": _raw_column(row, ("SPMS Status", "SPMS")),
            }
        )
    return normalized


def normalize_site_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        site_id = _raw_column(row, ("Site ID", "SiteID", "id"))
        if not site_id:
            continue
        lat_val = _raw_column(row, ("Latitude", "Lat OSS", "Lat NMS", "lat oss"))
        lng_val = _raw_column(row, ("Longitude", "Long OSS", "Long NMS", "long oss"))
        try:
            lat = float(lat_val)
        except (ValueError, TypeError):
            lat = None
        try:
            lng = float(lng_val)
        except (ValueError, TypeError):
            lng = None

        normalized.append(
            {
                **row,
                "siteId": site_id,
                "siteName": _raw_column(row, ("Site Name", "SiteName", "name")),
                "province": _raw_column(row, ("Province", "Provinsi", "Provinsi Lama")),
                "regency": _raw_column(row, ("Regency/City", "Kab/Kota", "Kabupaten/Kota")),
                "kecamatan": _raw_column(row, ("Kecamatan",)),
                "desa": _raw_column(row, ("Desa",)),
                "tipeTower": _raw_column(row, ("Tipe Tower", "Tower")),
                "tipePower": _raw_column(row, ("Tipe Power", "Power")),
                "consortium": _raw_column(row, ("Consortium", "Konsorsium Pembangunan", "Konsorsium")),
                "package": _raw_column(row, ("Package", "Paket", "Paket MSS 2026", "Opsel Area Package")),
                "state": _raw_column(row, ("State Condition", "Status On Air", "Status", "State")),
                "latitude": lat_val,
                "longitude": lng_val,
                "lat": lat,
                "lng": lng,
                "latOss": lat_val,
                "lngOss": lng_val,
                "opsel": _raw_column(row, ("Opsel",)),
            }
        )
    return normalized


def normalize_performance_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    availability_column = re.compile(
        r"^availability\s*[-–]\s*(\d{4})[-]?(\d{2})[-]?(\d{2})$",
        re.IGNORECASE,
    )
    columns: list[tuple[str, str]] = []
    if rows:
        for header in rows[0].keys():
            cleaned_h = header.strip()
            match_iso = availability_column.fullmatch(cleaned_h)
            if match_iso:
                year, month, day = match_iso.groups()
                columns.append((f"{year}-{month}-{day}", cleaned_h))
            else:
                match_8 = re.search(r"(?:^|[^\d])(\d{8})(?:[^\d]|$)", cleaned_h)
                if match_8:
                    date_str = match_8.group(1)
                    formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    columns.append((formatted, cleaned_h))

    valid_dates = sorted({d for d, _ in columns})

    normalized = []
    for row in rows:
        site_id = _raw_column(row, ("Site ID", "SiteID", "id"))
        if not site_id:
            continue
        daily_availability = {}
        for date_str, header in columns:
            val = _percent(row.get(header))
            if val is not None:
                daily_availability[date_str] = val

        lat_val = _raw_column(row, ("Latitude", "Lat OSS", "Lat NMS", "lat oss"))
        lng_val = _raw_column(row, ("Longitude", "Long OSS", "Long NMS", "long oss"))
        try:
            lat = float(lat_val)
        except (ValueError, TypeError):
            lat = None
        try:
            lng = float(lng_val)
        except (ValueError, TypeError):
            lng = None

        normalized.append(
            {
                **row,
                "siteId": site_id,
                "siteName": _raw_column(row, ("Site Name", "SiteName", "name")),
                "package": _raw_column(row, ("Package", "Paket", "Paket MSS 2026", "Opsel Area Package")),
                "consortium": _raw_column(row, ("Consortium", "Konsorsium Pembangunan", "Konsorsium")),
                "province": _raw_column(row, ("Province", "Provinsi", "Provinsi Lama")),
                "latitude": lat_val,
                "longitude": lng_val,
                "lat": lat,
                "lng": lng,
                "opsel": _raw_column(row, ("Opsel",)),
                "dailyAvail": daily_availability,
            }
        )
    return normalized, valid_dates


# ── Trouble Ticket Analysis ───────────────────────────────────────────
def calculate_aging(ticket: dict[str, Any], now_ts: float | None = None) -> tuple[str, str, str, float]:
    """Returns (bucket, label, badge_type, hours)."""
    status = str(ticket.get("status") or "").upper()
    if status != "OPEN":
        return "none", "-", "an", 0.0

    site_down = ticket.get("siteDownTimestamp") or ticket.get("siteDownTime")
    try:
        ts = float(site_down)
    except (TypeError, ValueError):
        ts = _parse_timestamp(site_down)
    if not ts:
        return "d1", "<1 Hari", "aok", 0.0

    current = now_ts or time.time()
    diff_hours = (current - ts) / 3600.0
    if diff_hours < 24:
        return "d1", "<1 Hari", "aok", diff_hours
    if diff_hours < 72:
        return "d3", "1–3 Hari", "awk", diff_hours
    if diff_hours < 168:
        return "d7", "3–7 Hari", "a7", diff_hours
    return "max", ">7 Hari", "am", diff_hours


def calculate_aging_counts(open_tickets: list[dict[str, Any]], now_ts: float | None = None) -> dict[str, int]:
    counts = {"ALL": len(open_tickets), "d1": 0, "d3": 0, "d7": 0, "max": 0}
    for t in open_tickets:
        bucket, _, _, _ = calculate_aging(t, now_ts)
        if bucket in counts:
            counts[bucket] += 1
    return counts


def build_escalation_items(open_tickets: list[dict[str, Any]], now_ts: float | None = None) -> list[dict[str, Any]]:
    items = []
    for t in open_tickets:
        bucket, label, _, hours = calculate_aging(t, now_ts)
        if bucket == "max":
            items.append({"ticket": t, "level": 3, "level_label": "LEVEL 3 >7H", "color": "#f43f5e", "hours": hours})
        elif bucket == "d7":
            items.append({"ticket": t, "level": 2, "level_label": "LEVEL 2 3–7H", "color": "#fb923c", "hours": hours})
        elif bucket == "d3":
            items.append({"ticket": t, "level": 1, "level_label": "LEVEL 1 1–3H", "color": "#fbbf24", "hours": hours})

    items.sort(key=lambda x: x["hours"], reverse=True)
    return items


def generate_auto_insights(open_tickets: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not open_tickets:
        return [{"color": "#10b981", "text": "✅ Tidak ada open ticket dalam filter saat ini"}]

    insights = []
    problems: dict[str, int] = {}
    for t in open_tickets:
        p = t.get("problem") or "Other"
        problems[p] = problems.get(p, 0) + 1

    if problems:
        top_prob, count = max(problems.items(), key=lambda kv: kv[1])
        pct = round((count / len(open_tickets)) * 100)
        insights.append({
            "color": "#22d3ee",
            "text": f"🔧 Top problem: <b>{top_prob}</b> ({count} — {pct}%)"
        })

    aging_counts = calculate_aging_counts(open_tickets)
    if aging_counts["max"] > 0:
        insights.append({
            "color": "#f43f5e",
            "text": f"⏰ <b>{aging_counts['max']} site</b> aging >7 hari — butuh eskalasi segera"
        })

    corrs = calculate_incident_correlation(open_tickets)
    if corrs:
        top_c = corrs[0]
        insights.append({
            "color": "#fb923c" if top_c["severity"] == "HIGH" else "#fbbf24",
            "text": f"🚨 <b>{top_c['count']} site down bersamaan</b> di {top_c['regency']} ({top_c['top_problem']}) — Potensi Hub/Regional outage",
        })

    return insights


def calculate_sla_status(
    ticket: dict[str, Any],
    target_hours: float = 4.0,
    now_ts: float | None = None,
) -> tuple[str, str, float, str]:
    """Returns (status, badge_label, remaining_hours, color).
    status: 'CLOSED', 'BREACHED', 'CRITICAL' (<1h), 'WARNING' (<2h), 'NORMAL' (>=2h)
    """
    status = str(ticket.get("status") or "").upper()
    if status != "OPEN":
        return "CLOSED", "CLOSED", 0.0, "#10b981"

    site_down = ticket.get("siteDownTimestamp") or ticket.get("siteDownTime")
    try:
        ts = float(site_down)
    except (TypeError, ValueError):
        ts = _parse_timestamp(site_down)
    if not ts:
        return "NORMAL", f"Target {int(target_hours)}h", target_hours, "#10b981"

    current = now_ts or time.time()
    elapsed_hours = (current - ts) / 3600.0
    rem_hours = target_hours - elapsed_hours

    if rem_hours <= 0:
        over_h = abs(rem_hours)
        if over_h >= 24:
            d = int(over_h // 24)
            h = int(over_h % 24)
            lbl = f"-{d}d {h}h (BREACHED)"
        else:
            h = int(over_h)
            m = int((over_h - h) * 60)
            lbl = f"-{h}h {m}m (BREACHED)"
        return "BREACHED", lbl, rem_hours, "#f43f5e"

    if rem_hours < 1.0:
        m = int(rem_hours * 60)
        return "CRITICAL", f"Sisa {m}m", rem_hours, "#f43f5e"
    if rem_hours < 2.0:
        m = int((rem_hours - 1.0) * 60)
        return "WARNING", f"Sisa 1h {m}m", rem_hours, "#fbbf24"

    h = int(rem_hours)
    return "NORMAL", f"Sisa {h}h", rem_hours, "#10b981"


def calculate_incident_correlation(open_tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups down sites by regency and problem to identify potential regional outages / Hub failures."""
    regency_groups: dict[str, list[dict[str, Any]]] = {}
    for t in open_tickets:
        reg = str(t.get("regency") or t.get("province") or "Unknown").strip()
        regency_groups.setdefault(reg, []).append(t)

    correlations = []
    for reg, group in regency_groups.items():
        if len(group) >= 2:
            problems: dict[str, int] = {}
            for t in group:
                p = str(t.get("problem") or "Other")
                problems[p] = problems.get(p, 0) + 1
            top_p, count = max(problems.items(), key=lambda kv: kv[1])
            correlations.append({
                "regency": reg,
                "count": len(group),
                "top_problem": top_p,
                "sites": [t.get("siteId") for t in group if t.get("siteId")],
                "severity": "HIGH" if len(group) >= 4 else "MEDIUM",
            })
    correlations.sort(key=lambda x: x["count"], reverse=True)
    return correlations


def calculate_top10_sites(tickets: list[dict[str, Any]], problem_filter: str = "ALL") -> list[dict[str, Any]]:
    site_stats: dict[str, dict[str, Any]] = {}
    for t in tickets:
        sid = t.get("siteId")
        if not sid:
            continue
        if sid not in site_stats:
            site_stats[sid] = {
                "siteId": sid,
                "siteName": t.get("siteName", ""),
                "package": t.get("package", ""),
                "ticketId": t.get("ticketId", "-"),
                "open": 0,
                "closed": 0,
                "problems": {},
            }
        entry = site_stats[sid]
        if str(t.get("status", "")).upper() == "OPEN":
            entry["open"] += 1
        else:
            entry["closed"] += 1
        p = t.get("problem") or "Other"
        entry["problems"][p] = entry["problems"].get(p, 0) + 1
        if t.get("ticketId"):
            entry["ticketId"] = t["ticketId"]

    results = []
    for sid, s in site_stats.items():
        total = s["open"] + s["closed"]
        prob_count = total if problem_filter == "ALL" else s["problems"].get(problem_filter, 0)
        results.append({**s, "total": total, "probCount": prob_count})

    results.sort(key=lambda x: x["total"], reverse=True)
    return results[:10]


# ── Shift Handover & NOC Report Generators ────────────────────────────
def generate_shift_handover(
    tickets: list[dict[str, Any]],
    area: str = "all",
    spreadsheet_url: str = "https://docs.google.com/spreadsheets/d/10M20JUr2CiCtz3LvrmcJn8e6p4ND0UvwLqE0Z_p9HL4/edit?gid=1631492418",
    pagi: str = "",
    malam: str = "",
    time_str: str = "",
    include_list: bool = False,
) -> str:
    now = datetime.now()
    months = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    tanggal_str = f"{now.day} {months[now.month - 1]} {now.year}"
    if not time_str:
        hh = now.hour
        jam_report = "06:00" if 3 <= hh < 9 else "12:00" if 9 <= hh < 15 else "18:00" if 15 <= hh < 21 else "00:00"
    else:
        jam_report = time_str

    area_label = {"all": "NOC ALL AREA", "maluku": "NOC MALUKU", "papua": "NOC PAPUA"}.get(area, "NOC ALL AREA")

    def _match_area(t: dict[str, Any]) -> bool:
        if area == "all":
            return True
        prov = str(t.get("province", "")).lower()
        pkg = str(t.get("package", "")).lower()
        cons = str(t.get("consortium", "")).lower()
        if area == "maluku":
            return "maluku" in prov or "10" in pkg or "maluku" in cons
        if area == "papua":
            return "papua" in prov or "11" in pkg or "papua" in cons
        return True

    open_tickets = [t for t in tickets if str(t.get("status", "")).upper() == "OPEN" and _match_area(t)]
    ag = calculate_aging_counts(open_tickets)

    text = (
        f"{area_label}\n"
        f"Shift Handover tanggal {tanggal_str} {jam_report} WIB\n"
        f"Pagi  : {pagi}\n"
        f"Malam : {malam}\n"
        f"{spreadsheet_url}\n\n"
        f"Summary TT Open\n"
        f"Total TT Open    : {len(open_tickets)} site\n"
        f"TT Open < 1 hari : {ag['d1']} site\n"
        f"TT Open 1-3 Hari : {ag['d3']} site\n"
        f"TT Open 3-7 Hari : {ag['d7']} site\n"
        f"TT Open > 7 Hari : {ag['max']} site"
    )

    if include_list and open_tickets:
        text += "\n\nDaftar Site Open:\n"
        for i, t in enumerate(open_tickets, 1):
            sid = t.get("siteId", "")
            sname = t.get("siteName", "")
            prob = t.get("problem", "-")
            dur = t.get("siteDownTime", "-")
            text += f"{i}. {sid} - {sname} | {prob} ({dur})\n"

    return text


def generate_noc_report(
    tickets: list[dict[str, Any]],
    area: str = "all",
    time_str: str = "12:00",
    date_str: str = "",
    spreadsheet_url: str = "https://docs.google.com/spreadsheets/d/10M20JUr2CiCtz3LvrmcJn8e6p4ND0UvwLqE0Z_p9HL4/edit?gid=1631492418",
    include_list: bool = False,
) -> str:
    if not date_str:
        now = datetime.now()
        months = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        date_str = f"{now.day} {months[now.month - 1]} {now.year}"

    area_label = {"all": "NOC ALL AREA", "maluku": "NOC MALUKU", "papua": "NOC PAPUA"}.get(area, "NOC ALL AREA")

    def _match_area(t: dict[str, Any]) -> bool:
        if area == "all":
            return True
        prov = str(t.get("province", "")).lower()
        pkg = str(t.get("package", "")).lower()
        cons = str(t.get("consortium", "")).lower()
        if area == "maluku":
            return "maluku" in prov or "10" in pkg or "maluku" in cons
        if area == "papua":
            return "papua" in prov or "11" in pkg or "papua" in cons
        return True

    open_tickets = [t for t in tickets if str(t.get("status", "")).upper() == "OPEN" and _match_area(t)]
    ag = calculate_aging_counts(open_tickets)

    text = (
        f"{area_label}\n"
        f"Berikut Site Problem TT CM {date_str} {time_str} WIB\n"
        f"{spreadsheet_url}\n\n"
        f"Summary TT Open\n"
        f"Total TT Open    : {len(open_tickets)} site\n"
        f"TT Open < 1 hari : {ag['d1']} site\n"
        f"TT Open 1-3 Hari : {ag['d3']} site\n"
        f"TT Open 3-7 Hari : {ag['d7']} site\n"
        f"TT Open > 7 Hari : {ag['max']} site"
    )

    if include_list and open_tickets:
        text += "\n\nDaftar Site Open:\n"
        for i, t in enumerate(open_tickets, 1):
            sid = t.get("siteId", "")
            sname = t.get("siteName", "")
            prob = t.get("problem", "-")
            dur = t.get("siteDownTime", "-")
            text += f"{i}. {sid} - {sname} | {prob} ({dur})\n"

    return text


# ── Performance & Summary Analytics ──────────────────────────────────
def calculate_availability_distribution(
    performance_rows: list[dict[str, Any]], date_str: str | None
) -> dict[str, int]:
    buckets = {"≥99%": 0, "95–99%": 0, "90–95%": 0, "<90%": 0}
    if not date_str:
        return buckets
    for row in performance_rows:
        val = (row.get("dailyAvail") or {}).get(date_str)
        if val is None:
            continue
        if val >= 99.0:
            buckets["≥99%"] += 1
        elif val >= 95.0:
            buckets["95–99%"] += 1
        elif val >= 90.0:
            buckets["90–95%"] += 1
        else:
            buckets["<90%"] += 1
    return buckets


def calculate_province_availability(
    performance_rows: list[dict[str, Any]], date_str: str | None
) -> list[tuple[str, float]]:
    if not date_str:
        return []
    prov_data: dict[str, list[float]] = {}
    for row in performance_rows:
        prov = str(row.get("province") or "").strip()
        if not prov:
            continue
        val = (row.get("dailyAvail") or {}).get(date_str)
        if val is not None:
            prov_data.setdefault(prov, []).append(float(val))

    results = []
    for prov, values in prov_data.items():
        if values:
            results.append((prov, round(sum(values) / len(values), 2)))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def calculate_correlation(
    performance_rows: list[dict[str, Any]],
    tickets: list[dict[str, Any]],
    date_str: str | None,
) -> list[dict[str, Any]]:
    open_counts: dict[str, int] = {}
    for t in tickets:
        if str(t.get("status", "")).upper() == "OPEN":
            sid = str(t.get("siteId", "")).strip()
            if sid:
                open_counts[sid] = open_counts.get(sid, 0) + 1

    correlations = []
    for row in performance_rows:
        sid = str(row.get("siteId", "")).strip()
        if not sid:
            continue
        val = (row.get("dailyAvail") or {}).get(date_str or "")
        open_tt = open_counts.get(sid, 0)

        # Include if has open TT or low availability (<95%)
        if open_tt > 0 or (val is not None and val < 95.0):
            risk = "HIGH" if (open_tt > 0 and val is not None and val < 95.0) else "MED" if open_tt > 0 else "LOW"
            correlations.append({
                "siteId": sid,
                "siteName": row.get("siteName", ""),
                "province": row.get("province", ""),
                "package": row.get("package", ""),
                "openTT": open_tt,
                "avail": val,
                "risk": risk,
            })

    correlations.sort(key=lambda x: (x["risk"] != "HIGH", -x["openTT"]))
    return correlations


def calculate_weekly_availability(
    performance_rows: list[dict[str, Any]],
    valid_dates: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    # Group dates by ISO week
    week_map: dict[str, list[str]] = {}
    for d_str in valid_dates:
        try:
            d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
            iso_year, iso_week, _ = d_obj.isocalendar()
            wk_key = f"W{iso_week:02d} {iso_year}"
            week_map.setdefault(wk_key, []).append(d_str)
        except Exception:
            continue

    weeks = sorted(week_map.keys(), reverse=True)[:8]

    rows = []
    for site in performance_rows[:60]:
        avail_map = site.get("dailyAvail") or {}
        week_vals = {}
        for w in weeks:
            dates = week_map.get(w, [])
            vals = [avail_map[d] for d in dates if d in avail_map]
            week_vals[w] = round(sum(vals) / len(vals), 1) if vals else None
        rows.append({
            "siteId": site.get("siteId", ""),
            "siteName": site.get("siteName", ""),
            "weeks": week_vals,
        })

    return weeks, rows


def summarize_dashboard(
    tickets: list[dict[str, Any]],
    performance: list[dict[str, Any]],
    selected_date: str | None,
    group_by: str = "package",
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}

    def _get_key(item: dict[str, Any]) -> str:
        if group_by == "province":
            return str(item.get("province") or "Tidak diketahui").strip()
        raw_pkg = str(item.get("package") or "Tidak diketahui").strip()
        return norm_pkg(raw_pkg)

    for site in performance:
        key = _get_key(site)
        group = groups.setdefault(
            key,
            {"group": key, "sites": 0, "available": [], "ok": 0, "critical": 0},
        )
        group["sites"] += 1
        availability = (site.get("dailyAvail") or {}).get(selected_date or "")
        if isinstance(availability, (int, float)):
            group["available"].append(float(availability))
            group["ok"] += availability >= 99
            group["critical"] += availability < 95

    ticket_counts: dict[str, dict[str, int]] = {}
    for ticket in tickets:
        key = _get_key(ticket)
        status = str(ticket.get("status") or "").upper()
        counts = ticket_counts.setdefault(key, {"OPEN": 0, "CLOSED": 0})
        counts["OPEN" if status == "OPEN" else "CLOSED"] += 1

    summaries = []
    for key, group in groups.items():
        values = group.pop("available")
        group["openTickets"] = ticket_counts.get(key, {}).get("OPEN", 0)
        group["closedTickets"] = ticket_counts.get(key, {}).get("CLOSED", 0)
        group["averageAvailability"] = (
            sum(values) / len(values) if values else None
        )
        summaries.append(group)
    return sorted(summaries, key=lambda row: row["group"].casefold())


# ── Backwards compatibility for Ticket Checker exports ─────────────────
GAP_EXPORT_HEADERS = [
    "No", "Site ID", "Site Name", "Site ID OPSEL", "Province", "Regency/City",
    "Consortium", "Vendor MSS", "MSS Package", "Opsel", "Package",
    "Opsel Area Package", "Alarm ID", "Alarm Title", "Ticket ID",
    "Ticket Duration", "State Condition", "Status Planned",
    "Site Down Duration", "Date Time Site Down", "Down Duration Category",
    "Force Majeure Status", "Status", "Administrative State 1",
    "Administrative State 2", "Operation State", "Root Cause Analysis",
    "Root Cause Description",
]


def read_incident_file(path: str | Path) -> tuple[list[str], list[dict[str, Any]]]:
    from WebTicketChecker.data import read_incident_file as _read
    records = _read(path)
    headers = list(records[0].keys()) if records else []
    return headers, records


def compare_ticket_gaps(
    database_rows: list[dict[str, Any]],
    down_rows: list[dict[str, Any]],
    unmonitor_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from WebTicketChecker.data import audit_both_incident_files
    return audit_both_incident_files(database_rows, down_rows, unmonitor_rows)


def gap_export_rows(gaps: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = [GAP_EXPORT_HEADERS]
    for index, gap in enumerate(gaps, start=1):
        raw = gap.get("raw") or gap.get("_raw") or gap
        output: list[Any] = []
        for column in GAP_EXPORT_HEADERS:
            if column == "No":
                output.append(index)
                continue
            if column == "Site Down Duration":
                val = raw.get("Site Down Duration") or raw.get("Site Unmonitor Duration") or raw.get("Duration") or ""
                output.append(val)
                continue
            if column == "Date Time Site Down":
                val = raw.get("Date Time Site Down") or raw.get("Date Time Site Unmonitor") or raw.get("Down Time") or ""
                output.append(val)
                continue
            if column == "Down Duration Category":
                val = raw.get("Down Duration Category") or raw.get("Unmonitor Duration Category") or raw.get("Duration Category") or ""
                output.append(val)
                continue
            output.append(raw.get(column, "") if raw.get(column) is not None else "")
        rows.append(output)
    return rows


def write_gap_workbook(path: str | Path, gaps: list[dict[str, Any]]) -> None:
    from WebTicketChecker.data import write_gap_workbook as _write
    _write(gaps, path)
