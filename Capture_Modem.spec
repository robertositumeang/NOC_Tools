# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()
MODEM_DIR = ROOT / "Capture_Modem"

datas = [
    (str(ROOT / "app_icon.ico"), "."),
    (
        str(ROOT / "contoh_template" / "Template_Sitelist_Capture_Modem.xlsx"),
        "contoh_template",
    ),
]
mapping_folder = MODEM_DIR / "mapping Ip Modem by site id"
if mapping_folder.exists():
    datas.append((str(mapping_folder), "mapping Ip Modem by site id"))

binaries = []
hiddenimports = [
    "launch_guard",
    "noc_brand",
    "capture_engine",
    "ip_lookup",
    "embedded_sites",
    "openpyxl",
    "bs4",
    "soupsieve",
    "requests",
    "PyQt6",
]

for pkg in ["playwright", "greenlet", "pyee"]:
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    [str(MODEM_DIR / "gui_app.py")],
    pathex=[str(ROOT), str(MODEM_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pandas",
        "numpy",
        "pyarrow",
        "sqlalchemy",
        "psycopg2",
        "duckdb",
        "altair",
        "plotly",
        "narwhals",
        "polars",
        "lz4",
        "matplotlib",
        "scipy",
        "tkinter",
        "_tkinter",
        "PyQt5",
        "flask",
        "flask_login",
        "bottle",
        "jupyterlab",
        "notebook",
        "ipython",
        "ipykernel",
        "ipywidgets",
        "nbconvert",
        "nbformat",
        "streamlit",
        "pytest",
        "_pytest",
        "fonttools",
        "pydeck",
        "zstandard",
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Capture_Modem",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "app_icon.ico")],
)
