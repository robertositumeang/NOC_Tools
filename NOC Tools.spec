from pathlib import Path

ROOT = Path(SPECPATH)
CCTV_DIR = ROOT / 'CCTV_Report'
MASTER_FILES = list(ROOT.glob('Site Management*.xlsx'))
if not MASTER_FILES:
    raise FileNotFoundError('Site Management*.xlsx tidak ditemukan.')
MASTER_FILE = max(MASTER_FILES, key=lambda path: path.stat().st_mtime)
EXAMPLE_TEMPLATES = ROOT / 'contoh_template'

# Library besar yang tidak dipakai — wajib dikecualikan
_EXCLUDES = [
    # Data science (tidak dipakai)
    "pandas", "numpy", "pyarrow", "polars", "narwhals",
    "duckdb", "sqlalchemy", "alembic",
    # Visualisasi alternatif (tidak dipakai)
    "altair", "plotly", "streamlit", "bokeh",
    # DB connectors (tidak dipakai)
    "psycopg2", "mysql", "mysql_connector", "clickhouse_connect",
    # Web framework alternatif (tidak dipakai — project pakai FastAPI)
    "flask", "flask_login", "bottle", "django",
    # Jupyter / IPython (tidak dipakai di exe)
    "jupyterlab", "notebook", "ipython", "ipykernel",
    "ipywidgets", "nbconvert", "nbformat",
    # Kompresi / format tidak dipakai
    "lz4", "zstandard", "rarfile",
    # Testing (tidak ikut ke production)
    "pytest", "_pytest",
    # GUI alternatif (project pakai PyQt6)
    "tkinter", "_tkinter", "PyQt5",
    # Matplotlib backends tidak dipakai
    "matplotlib.backends.backend_gtk3",
    "matplotlib.backends.backend_gtk3agg",
    "matplotlib.backends.backend_gtk4",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_tkagg",
    # Lainnya
    "scipy", "fonttools", "pydeck",
]

hiddenimports = [
    'pythoncom',
    'pywintypes',
    'win32com.client',
    'updater',
    'auth',
    'license_mgr',
    'launch_guard',
    'noc_brand',
    'desktop_app',
    'PIL.ImageStat',
]


a = Analysis(
    [str(ROOT / 'app.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(MASTER_FILE), 'site_management'),
        (str(CCTV_DIR / 'cctv_report_app.py'), 'CCTV_Report'),
        (str(CCTV_DIR / 'assets'), 'assets'),
        (str(EXAMPLE_TEMPLATES), 'contoh_template'),
        (str(ROOT / 'app_icon.ico'), '.'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
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
    name='NOC Tools',
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
    icon=[str(ROOT / 'app_icon.ico')],
)
