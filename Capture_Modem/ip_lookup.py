# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import glob
import csv
from pathlib import Path
from typing import Any, Iterator

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    from embedded_sites import EMBEDDED_SITES
except ImportError:
    EMBEDDED_SITES = []

MAPPING_DIR = os.path.join(os.path.dirname(__file__), 'mapping Ip Modem by site id')


class SiteList(list):
    """Lightweight list of site dicts replacing pandas DataFrame.
    Supports .empty, .iterrows(), and .to_dict() for full backward compatibility
    without requiring pandas, numpy, or pyarrow (saving ~190 MB).
    """
    @property
    def empty(self) -> bool:
        return len(self) == 0

    def iterrows(self) -> Iterator[tuple[int, dict[str, Any]]]:
        for idx, item in enumerate(self):
            yield idx, item

    def to_dict(self, orient: str = 'records') -> list[dict[str, Any]]:
        return list(self)


def _read_excel_rows(file_path: str) -> list[dict[str, Any]]:
    if not openpyxl:
        return []
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    sheet = wb.active
    rows = sheet.iter_rows(values_only=True)
    
    first_row = next(rows, None)
    if not first_row:
        return []
        
    headers = [str(c).strip() if c is not None else '' for c in first_row]
    result: list[dict[str, Any]] = []
    for r in rows:
        if not r or not any(r):
            continue
        d = {headers[i]: r[i] for i in range(min(len(headers), len(r))) if headers[i]}
        result.append(d)
    return result


def _read_csv_rows(file_path: str) -> list[dict[str, Any]]:
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        sample = f.read(4096)
        f.seek(0)
        
        # Detect delimiter
        delimiter = ','
        if ';' in sample and sample.count(';') > sample.count(','):
            delimiter = ';'
        elif '\t' in sample and sample.count('\t') > sample.count(','):
            delimiter = '\t'
            
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            return []
            
        clean_fieldnames = {fn: str(fn).strip() for fn in reader.fieldnames if fn}
        result: list[dict[str, Any]] = []
        for row in reader:
            clean_row = {clean_fieldnames[k]: v for k, v in row.items() if k in clean_fieldnames and v is not None}
            if any(clean_row.values()):
                result.append(clean_row)
        return result


def _normalize_row_columns(row: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {'Site ID': '', 'Site Name': '', 'IP': ''}
    for col_name, val in row.items():
        if val is None:
            continue
        val_str = str(val).strip()
        cl = str(col_name).strip().lower()
        if any(k in cl for k in ['site id', 'siteid', 'site_id', 'id site', 'site']):
            if not normalized['Site ID']:
                normalized['Site ID'] = val_str
        elif any(k in cl for k in ['site name', 'sitename', 'site_name', 'nama', 'name']):
            if not normalized['Site Name']:
                normalized['Site Name'] = val_str
        elif any(k in cl for k in ['ip', 'ip modem', 'ip address', 'host']):
            if not normalized['IP']:
                normalized['IP'] = val_str
    return normalized


def load_site_mapping() -> SiteList:
    records: list[dict[str, Any]] = []
    
    # 1. Search in mapping directory or current directory
    search_dirs = [MAPPING_DIR, os.path.dirname(__file__)]
    files = []
    for d in search_dirs:
        if os.path.exists(d):
            files.extend(glob.glob(os.path.join(d, '*.xlsx')))
            files.extend(glob.glob(os.path.join(d, '*.xls')))
            files.extend(glob.glob(os.path.join(d, '*.csv')))

    files = list(set(files))

    seen_sites = set()
    for f in files:
        if os.path.basename(f).startswith('~$'):
            continue
        try:
            if f.endswith(('.xlsx', '.xls')):
                rows = _read_excel_rows(f)
            else:
                rows = _read_csv_rows(f)

            for r in rows:
                norm = _normalize_row_columns(r)
                sid = norm['Site ID'].upper()
                if sid and sid not in seen_sites and norm['IP']:
                    seen_sites.add(sid)
                    records.append({
                        'Site ID': sid,
                        'Site Name': norm['Site Name'],
                        'IP': norm['IP'],
                        'Source File': os.path.basename(f),
                    })
        except Exception as e:
            print(f'Error reading {f}: {e}')

    if records:
        return SiteList(records)

    # 2. Fallback to EMBEDDED_SITES (Guarantees portability to other laptops even without Excel file!)
    if EMBEDDED_SITES:
        result = []
        for s in EMBEDDED_SITES:
            sid = str(s.get('Site ID', '')).strip().upper()
            if sid and sid not in seen_sites:
                seen_sites.add(sid)
                result.append({
                    'Site ID': sid,
                    'Site Name': str(s.get('Site Name', '')).strip(),
                    'IP': str(s.get('IP', '')).strip(),
                    'Source File': 'Embedded Database (Portable)',
                })
        return SiteList(result)

    return SiteList()


def lookup_site(site_query: str, mapping_list: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    if mapping_list is None:
        mapping_list = load_site_mapping()

    if not mapping_list:
        return None

    query = str(site_query).strip().upper()
    
    # 1. Exact Site ID match
    for item in mapping_list:
        if item.get('Site ID', '').upper() == query:
            return item

    # 2. Substring Site ID match
    for item in mapping_list:
        if query in item.get('Site ID', '').upper():
            return item

    # 3. Substring Site Name match
    for item in mapping_list:
        if query in str(item.get('Site Name', '')).upper():
            return item

    return None


def get_ip_for_site(site_id: str, mapping_list: list[dict[str, Any]] | None = None) -> str:
    res = lookup_site(site_id, mapping_list)
    if res and res.get('IP'):
        return str(res['IP']).strip()
    return "10.70.1.225"


def parse_imported_sitelist_file(file_path: str, mapping_list: list[dict[str, Any]] | None = None) -> SiteList:
    """Parses an imported file (.xlsx, .xls, .csv, .txt) containing sitelist,
    normalizes columns to ['Site ID', 'Site Name', 'IP'], and enriches with mapping_list if needed.
    """
    if mapping_list is None:
        mapping_list = load_site_mapping()
        
    ext = os.path.splitext(file_path)[1].lower()
    raw_rows: list[dict[str, Any]] = []

    if ext in ['.xlsx', '.xls']:
        raw_rows = _read_excel_rows(file_path)
    elif ext == '.csv':
        raw_rows = _read_csv_rows(file_path)
    elif ext == '.txt':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                sid = line.strip()
                if sid:
                    raw_rows.append({'Site ID': sid})
    else:
        raise ValueError(f"File format {ext} is not supported")

    if not raw_rows:
        return SiteList()

    # Build DB lookup cache for fast enrichment
    db_lookup: dict[str, dict[str, str]] = {}
    if mapping_list:
        for r in mapping_list:
            sid = str(r.get('Site ID', '')).strip().upper()
            if sid:
                db_lookup[sid] = {
                    'Site Name': str(r.get('Site Name', '')).strip(),
                    'IP': str(r.get('IP', '')).strip()
                }

    result_rows: list[dict[str, Any]] = []
    seen_sids = set()

    for row in raw_rows:
        norm = _normalize_row_columns(row)
        sid = norm['Site ID'].upper()
        if not sid or sid in ['SITE ID', 'SITEID', 'NAN', 'NONE', ''] or sid in seen_sids:
            continue
            
        name = norm['Site Name']
        if name.lower() in ['nan', 'none']:
            name = ''
            
        ip = norm['IP']
        if ip.lower() in ['nan', 'none']:
            ip = ''

        # If IP or Name missing, look up in database
        if sid in db_lookup:
            if not ip or ip in ('Unknown IP', 'IP Tidak Diketahui'):
                ip = db_lookup[sid]['IP']
            if not name:
                name = db_lookup[sid]['Site Name']
        elif len(sid) >= 5:
            for db_sid, val in db_lookup.items():
                if sid == db_sid or (len(sid) >= 7 and sid in db_sid):
                    if not ip or ip in ('Unknown IP', 'IP Tidak Diketahui'):
                        ip = val['IP']
                    if not name:
                        name = val['Site Name']
                    break

        if not ip:
            ip = "Unknown IP"
        if not name:
            name = sid

        seen_sids.add(sid)
        result_rows.append({
            'Site ID': sid,
            'Site Name': name,
            'IP': ip
        })

    return SiteList(result_rows)
