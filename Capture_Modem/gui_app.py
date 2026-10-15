# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QComboBox, QCompleter,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QProgressBar,
    QFileDialog, QMessageBox, QFrame, QScrollArea, QSplitter, QSizePolicy,
    QStackedWidget, QButtonGroup, QGridLayout, QToolButton
)
from PyQt6.QtGui import QFont, QPixmap, QColor, QCursor, QPalette, QIcon, QPainter

# ── Security: harus dijalankan melalui NOC Tools.exe (setelah login) ──
_APP_ROOT = Path(__file__).resolve().parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
try:
    from launch_guard import require_launcher_token
    require_launcher_token("Capture Modem")
except SystemExit:
    raise          # tolak akses jika token tidak valid
except Exception:
    pass           # fallback saat development / run langsung dari source

import capture_engine
import ip_lookup
import noc_brand
from noc_brand import (
    DARK_THEME, LIGHT_THEME, THEMES, NocLogoMark, ThemeSelector,
    apply_standard_window_chrome
)
try:
    from noc_brand import paint_network_background
except ImportError:
    def paint_network_background(painter, bounds, is_dark=True, opacity=0.50):
        pass

# ================= COMTECH HIERARCHICAL MENU TREE =================
MENU_TREE = {
    "Home": {
        "sub": {
            "Home": {"page": "home.htm"},
            "Contact": {"page": "contact.htm"},
            "Features": {"page": "features.htm"}
        }
    },
    "Admin": {
        "sub": {
            "Access": {"page": "admin_access.htm"},
            "Users": {"page": "user.htm"},
            "Date & Time": {"page": "time.htm"},
            "Certificate": {"page": "cert.htm"}
        }
    },
    "Configuration": {
        "sub": {
            "Interface": {
                "sub": {
                    "GE1": {"page": "ge1.htm"},
                    "Management": {"page": "femgt.htm"}
                }
            },
            "WAN": {
                "sub": {
                    "Demod": {
                        "sub": {
                            "Tuner": {"page": "tuner1.htm"},
                            "ACM": {"page": "rx_acm.htm"}
                        }
                    },
                    "Mod": {
                        "sub": {
                            "Config": {"page": "mod.htm"},
                            "ACM": {"page": "acm.htm"},
                            "DPC": {
                                "sub": {
                                    "DPC": {"page": "dpc.htm"},
                                    "Commission": {"page": "commission.htm"}
                                }
                            }
                        }
                    },
                    "QoS": {
                        "sub": {
                            "Classifier": {"page": "pp_cfg_qos_classifier.htm"},
                            "Queue Group": {"page": "pp_cfg_qos_qg.htm"}
                        }
                    },
                    "Compression": {"page": "pp_status_trafficstats_compression.htm"},
                    "BUC": {"page": "buc.htm"},
                    "LNB": {"page": "lnb.htm"},
                    "WANOp": {"page": "pp_wanop_shaper.htm"}
                }
            },
            "Network": {
                "sub": {
                    "VLAN": {"page": "vlan.htm"},
                    "Bridge": {"page": "bridging.htm"},
                    "Static Route": {"page": "staticroutes.htm"},
                    "OSPF": {"page": "ospf.htm"},
                    "BGP": {"page": "bgp.htm"}
                }
            },
            "ECM": {"page": "carrierid.htm"},
            "MEO": {"page": "meo.htm"},
            "Roaming": {"page": "workingmode.htm"}
        }
    },
    "Status": {
        "sub": {
            "Alarms": {"page": "alarms.htm"},
            "Events": {"page": "event.htm"},
            "Spectrum": {"page": "spectrum.htm"},
            "Constellation": {"page": "graph.htm"},
            "Statistics": {
                "sub": {
                    "Transmission": {"page": "stats.htm"},
                    "Ethernet": {"page": "ether_stats.htm"},
                    "Switch Traffic": {"page": "bridgingstats.htm"},
                    "WANOp Stats": {"page": "wanop_stats.htm"}
                }
            }
        }
    },
    "Utility": {
        "sub": {
            "Save": {"page": "save.htm"},
            "Firmware": {"page": "firmware.htm"},
            "Reboot": {"page": "reboot.htm"},
            "SNMP": {"page": "snmp.htm"},
            "NMS": {"page": "nms.htm"}
        }
    }
}

# Standar 3 NOC: Commission, DPC, Config (mod.htm)
DEFAULT_NOC_PAGES = [
    {"name": "Commission", "path": "commission.htm", "breadcrumb": "Configuration > WAN > Mod > DPC > Commission"},
    {"name": "DPC", "path": "dpc.htm", "breadcrumb": "Configuration > WAN > Mod > DPC > DPC"},
    {"name": "Config (mod.htm)", "path": "mod.htm", "breadcrumb": "Configuration > WAN > Mod > Config"}
]

def get_site_capture_dir(site_id: str) -> Path:
    downloads = Path.home() / "Downloads"
    today_str = datetime.now().strftime("%Y-%m-%d")
    clean_id = str(site_id).strip().upper() if site_id else "MANUAL"
    target_dir = downloads / "Capture Modem" / today_str / clean_id
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


# ================= AUTHENTIC COMTECH NAV BAR WIDGET =================
class ComtechNavBar(QWidget):
    page_selected = pyqtSignal(str, str)

    def __init__(self, theme_name: str = DARK_THEME, parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 2, 4, 2)
        self.layout.setSpacing(3)
        self.selected_path = ["Configuration", "WAN", "Mod", "DPC", "Commission"]
        self.render_menu()

    def set_theme(self, theme_name: str):
        self.theme_name = theme_name
        self.render_menu()

    def render_menu(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        current_level_dict = MENU_TREE
        current_selection_chain = []
        final_page = "home.htm"

        is_dark = (self.theme_name == DARK_THEME)
        active_btn_style = """
            QPushButton {
                background-color: #2AA8F2;
                border: 1.5px solid #58BDF8;
                color: #091526;
                font-weight: bold;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                padding: 3px 8px;
                border-radius: 4px;
            }
        """ if is_dark else """
            QPushButton {
                background-color: #126FE8;
                border: 1.5px solid #075CC7;
                color: #FFFFFF;
                font-weight: bold;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                padding: 3px 8px;
                border-radius: 4px;
            }
        """

        inactive_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: #A8B9CF;
                text-decoration: underline;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                padding: 3px 6px;
            }
            QPushButton:hover {
                color: #58BDF8;
                background-color: #172B48;
                border-radius: 4px;
            }
        """ if is_dark else """
            QPushButton {
                background: transparent;
                border: none;
                color: #52677F;
                text-decoration: underline;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                padding: 3px 6px;
            }
            QPushButton:hover {
                color: #126FE8;
                background-color: #EAF1F9;
                border-radius: 4px;
            }
        """

        sep_color = "#4C83E6" if is_dark else "#8FA3BC"

        depth = 0
        while current_level_dict and depth < 6:
            keys = list(current_level_dict.keys())
            if not keys:
                break

            chosen_key = None
            if depth < len(self.selected_path) and self.selected_path[depth] in keys:
                chosen_key = self.selected_path[depth]
            else:
                chosen_key = keys[0]
                if depth < len(self.selected_path):
                    self.selected_path[depth] = chosen_key
                else:
                    self.selected_path.append(chosen_key)

            current_selection_chain.append(chosen_key)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            for i, k in enumerate(keys):
                btn = QPushButton(k)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet(active_btn_style if k == chosen_key else inactive_btn_style)
                btn.clicked.connect(lambda checked, d=depth, name=k: self.on_button_clicked(d, name))
                row_layout.addWidget(btn)

                if i < len(keys) - 1:
                    sep = QLabel(" | ")
                    sep.setStyleSheet(f"color: {sep_color}; font-weight: bold; font-family: monospace; font-size: 12px;")
                    row_layout.addWidget(sep)

            self.layout.addWidget(row_widget)

            node = current_level_dict.get(chosen_key, {})
            if "page" in node:
                final_page = node["page"]

            if "sub" in node:
                current_level_dict = node["sub"]
                depth += 1
            else:
                break

        self.selected_path = current_selection_chain
        breadcrumb_str = " > ".join(self.selected_path)
        self.page_selected.emit(final_page, breadcrumb_str)

    def on_button_clicked(self, depth: int, name: str):
        self.selected_path = self.selected_path[:depth] + [name]
        self.render_menu()


# ================= CAPTURE WORKER THREAD =================
class CaptureWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    item_finished_signal = pyqtSignal(int, str, bool, str, list)
    all_finished_signal = pyqtSignal(int, int, bool, str, list)
    
    def __init__(self, tasks, username, password, is_single_site: bool = False):
        super().__init__()
        self.tasks = tasks
        self.username = username
        self.password = password
        self.is_single_site = is_single_site
        self.is_cancelled = False

    def run(self):
        total_sites = len(self.tasks)
        total_captures = sum(len(t.get("pages", [])) for t in self.tasks)
        processed_captures = 0
        success_sites = 0
        all_captured_files = []
        last_target_dir = ""
        
        for s_idx, task in enumerate(self.tasks):
            if self.is_cancelled:
                break
                
            site_id = task["site_id"]
            ip = task["ip"]
            pages = task.get("pages", [])
            row_idx = task.get("row_idx", -1)
            
            target_dir = get_site_capture_dir(site_id)
            last_target_dir = str(target_dir)
            site_success_count = 0
            site_saved_files = []
            
            for p_idx, page_info in enumerate(pages):
                if self.is_cancelled:
                    break
                    
                page_path = page_info["path"]
                page_name = page_info.get("name", page_path)
                
                processed_captures += 1
                percent = int((processed_captures / max(1, total_captures)) * 100)
                self.progress_signal.emit(
                    percent,
                    f"[{processed_captures}/{total_captures}] {site_id} ➔ {page_name}..."
                )
                
                clean_stem = page_path.replace(".htm", "").replace(".html", "").replace("pp_", "").replace("_", "")
                clean_name = f"{site_id}_{clean_stem}.png"
                out_file = str(target_dir / clean_name)
                
                res = capture_engine.capture_page(
                    host=ip,
                    page_path=page_path,
                    username=self.username,
                    password=self.password,
                    output_path=out_file
                )
                
                if res.get("success"):
                    site_success_count += 1
                    site_saved_files.append(out_file)
                    all_captured_files.append(out_file)
                time.sleep(0.3)

            is_full_success = (site_success_count == len(pages))
            if is_full_success:
                success_sites += 1
                self.item_finished_signal.emit(row_idx, site_id, True, str(target_dir), site_saved_files)
            else:
                summary_status = f"{site_success_count}/{len(pages)} photos"
                self.item_finished_signal.emit(row_idx, site_id, False, summary_status, site_saved_files)

        self.progress_signal.emit(100, f"Completed! {success_sites} of {total_sites} sites succeeded.")
        self.all_finished_signal.emit(
            total_sites, success_sites, self.is_single_site, last_target_dir, all_captured_files
        )

    def cancel(self):
        self.is_cancelled = True


# ================= MAIN WINDOW (NOC TOOLS DESIGN SYSTEM) =================
class ModemCaptureGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NOC Tools — Comtech Modem Capture Suite")
        apply_standard_window_chrome(self)
        self.resize(1360, 920)
        self.setMinimumSize(1100, 780)
        
        self.current_theme = DARK_THEME
        self.site_db = ip_lookup.load_site_mapping()
        self.imported_sites = []
        self.worker = None
        self.last_captured_images = []
        self.active_preview_idx = 0
        
        # Navigation page state
        self.active_page_path = "commission.htm"
        self.active_breadcrumb = "Configuration > WAN > Mod > DPC > Commission"
        self.active_page_name = "Commission"
        
        # Target pages (default 3 NOC: Commission, DPC, Config)
        self.selected_target_pages = [dict(p) for p in DEFAULT_NOC_PAGES]
        
        self.current_site_id = "PAB0840"
        self.current_site_name = "PUSUTILIGUM"
        self.current_ip = "10.70.1.225"
        
        self.init_ui()
        self.apply_theme(self.current_theme)

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 8, 14, 10)
        main_layout.setSpacing(8)

        # ---------------- 1. COMPACT BRAND HEADER CARD (SLIM HEIGHT) ----------------
        header_card = QFrame()
        header_card.setObjectName("header_card")
        header_card.setFixedHeight(50)
        header_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(14, 4, 14, 4)
        h_layout.setSpacing(10)

        # Compact NOC Twin Polygon Logo
        self.logo_mark = NocLogoMark(size=30)
        h_layout.addWidget(self.logo_mark)

        # Brand Titles on single compact line
        h_title_row = QHBoxLayout()
        h_title_row.setSpacing(8)
        self.lbl_title = QLabel("NOC Tools - Comtech Modem Capture (VPN Active)")
        self.lbl_title.setObjectName("brandTitle")
        self.lbl_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        h_title_row.addWidget(self.lbl_title)
        h_title_row.addStretch()
        h_layout.addLayout(h_title_row)

        # Theme Selector (Light / Dark toggle)
        self.theme_selector = ThemeSelector(self.current_theme)
        self.theme_selector.themeChanged.connect(self.apply_theme)
        h_layout.addWidget(self.theme_selector)

        # Utility Buttons
        self.btn_ping = QPushButton("📶 Test Ping")
        self.btn_ping.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ping.clicked.connect(self.check_ping)
        h_layout.addWidget(self.btn_ping)

        self.btn_folder = QPushButton("📂 Open Output Folder")
        self.btn_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_folder.clicked.connect(self.open_downloads_folder)
        h_layout.addWidget(self.btn_folder)

        main_layout.addWidget(header_card, 0)

        # ---------------- 2. MAIN 2-COLUMN DASHBOARD SPLITTER ----------------
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setHandleWidth(8)

        # ================= LEFT COLUMN: CONTROL & TARGET PANEL =================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # --- Card 1: Target Site Selection & Credentials ---
        card_target = QFrame()
        card_target.setObjectName("card")
        l_ct = QVBoxLayout(card_target)
        l_ct.setContentsMargins(14, 10, 14, 10)
        l_ct.setSpacing(8)

        lbl_sec1 = QLabel("1. TARGET SITE & CREDENTIALS")
        lbl_sec1.setObjectName("sectionTitle")
        l_ct.addWidget(lbl_sec1)

        # Segmented Tab Mode Selector
        mode_container = QFrame()
        mode_container.setObjectName("mode_container")
        mode_pill_box = QHBoxLayout(mode_container)
        mode_pill_box.setContentsMargins(4, 4, 4, 4)
        mode_pill_box.setSpacing(4)
        
        self.btn_mode_db = QPushButton("● Site Package 11")
        self.btn_mode_db.setObjectName("btn_mode_db")
        self.btn_mode_db.setCheckable(True)
        self.btn_mode_db.setChecked(True)
        self.btn_mode_db.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.btn_mode_batch = QPushButton("Import Sitelist (Excel/TXT)")
        self.btn_mode_batch.setObjectName("btn_mode_batch")
        self.btn_mode_batch.setCheckable(True)
        self.btn_mode_batch.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.btn_mode_manual = QPushButton("Manual IP")
        self.btn_mode_manual.setObjectName("btn_mode_manual")
        self.btn_mode_manual.setCheckable(True)
        self.btn_mode_manual.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_mode_db)
        self.mode_group.addButton(self.btn_mode_batch)
        self.mode_group.addButton(self.btn_mode_manual)
        
        self.btn_mode_db.clicked.connect(self.on_mode_changed)
        self.btn_mode_batch.clicked.connect(self.on_mode_changed)
        self.btn_mode_manual.clicked.connect(self.on_mode_changed)
        
        mode_pill_box.addWidget(self.btn_mode_db)
        mode_pill_box.addWidget(self.btn_mode_batch)
        mode_pill_box.addWidget(self.btn_mode_manual)
        l_ct.addWidget(mode_container)

        # Stacked Inputs
        self.stack_mode = QStackedWidget()

        # Mode 0: Search from 769 Sites (Site Paket 11)
        w_m0 = QWidget()
        l_m0 = QVBoxLayout(w_m0)
        l_m0.setContentsMargins(0, 0, 0, 0)
        l_m0.setSpacing(4)
        lbl_s0 = QLabel("Search Site ID / Name:")
        lbl_s0.setStyleSheet("font-weight: 600; font-size: 11px;")
        l_m0.addWidget(lbl_s0)

        self.combo_site = QComboBox()
        self.combo_site.setEditable(True)
        self.combo_site.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_site.setMinimumHeight(34)
        if not self.site_db.empty:
            site_options = [f"{row['Site ID']} - {row['Site Name']} ({row['IP']})" for _, row in self.site_db.iterrows()]
            self.combo_site.addItems(site_options)
            completer = QCompleter(site_options, self.combo_site)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self.combo_site.setCompleter(completer)
            for idx, opt in enumerate(site_options):
                if "PAB0840" in opt:
                    self.combo_site.setCurrentIndex(idx)
                    break
        self.combo_site.currentIndexChanged.connect(self.on_site_selected)
        l_m0.addWidget(self.combo_site)
        self.stack_mode.addWidget(w_m0)

        # Mode 1: Import Sitelist (excel/txt)
        w_m1 = QWidget()
        l_m1 = QVBoxLayout(w_m1)
        l_m1.setContentsMargins(0, 0, 0, 0)
        l_m1.setSpacing(4)
        self.btn_import_file = QPushButton("📁 Select Sitelist File (.xlsx, .csv, .txt)")
        self.btn_import_file.setMinimumHeight(34)
        self.btn_import_file.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_import_file.clicked.connect(self.browse_file)
        l_m1.addWidget(self.btn_import_file)

        self.lbl_batch_count = QLabel("No file selected (0 sites)")
        self.lbl_batch_count.setStyleSheet("color: #2AA8F2; font-weight: bold; font-size: 11px;")
        l_m1.addWidget(self.lbl_batch_count)
        self.stack_mode.addWidget(w_m1)

        # Mode 2: Manual IP
        w_m2 = QWidget()
        l_m2 = QHBoxLayout(w_m2)
        l_m2.setContentsMargins(0, 0, 0, 0)
        l_m2.setSpacing(6)
        lbl_mip = QLabel("IP:")
        lbl_mip.setStyleSheet("font-weight: 600;")
        l_m2.addWidget(lbl_mip)
        self.txt_manual_ip = QLineEdit("10.70.1.225")
        self.txt_manual_ip.setMinimumHeight(34)
        self.txt_manual_ip.textChanged.connect(self.on_manual_changed)
        l_m2.addWidget(self.txt_manual_ip)

        lbl_msid = QLabel("Site ID:")
        lbl_msid.setStyleSheet("font-weight: 600;")
        l_m2.addWidget(lbl_msid)
        self.txt_manual_sid = QLineEdit("MANUAL_SITE")
        self.txt_manual_sid.setMinimumHeight(34)
        self.txt_manual_sid.textChanged.connect(self.on_manual_changed)
        l_m2.addWidget(self.txt_manual_sid)
        self.stack_mode.addWidget(w_m2)

        l_ct.addWidget(self.stack_mode)

        # Active Site Badge Banner
        self.active_site_banner = QFrame()
        self.active_site_banner.setObjectName("active_site_banner")
        as_layout = QHBoxLayout(self.active_site_banner)
        as_layout.setContentsMargins(10, 5, 10, 5)
        as_layout.setSpacing(8)

        self.lbl_badge_sid = QLabel("PAB0840")
        self.lbl_badge_sid.setObjectName("badge_sid")
        as_layout.addWidget(self.lbl_badge_sid)

        self.lbl_badge_name = QLabel("PUSUTILIGUM")
        self.lbl_badge_name.setObjectName("badge_name")
        as_layout.addWidget(self.lbl_badge_name)

        self.lbl_badge_ip = QLabel("10.70.1.225:80")
        self.lbl_badge_ip.setObjectName("badge_ip")
        as_layout.addWidget(self.lbl_badge_ip)
        as_layout.addStretch()
        l_ct.addWidget(self.active_site_banner)

        # Credentials Row
        cred_row = QHBoxLayout()
        cred_row.setSpacing(6)
        lbl_port = QLabel("Port:")
        lbl_port.setStyleSheet("font-weight: 600; font-size: 11px;")
        cred_row.addWidget(lbl_port)
        self.txt_port = QLineEdit("80")
        self.txt_port.setFixedWidth(45)
        self.txt_port.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cred_row.addWidget(self.txt_port)

        lbl_user = QLabel("User:")
        lbl_user.setStyleSheet("font-weight: 600; font-size: 11px;")
        cred_row.addWidget(lbl_user)
        self.txt_user = QLineEdit("comtech")
        cred_row.addWidget(self.txt_user)

        lbl_pass = QLabel("Pass:")
        lbl_pass.setStyleSheet("font-weight: 600; font-size: 11px;")
        cred_row.addWidget(lbl_pass)
        self.txt_pass = QLineEdit("comtech")
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        cred_row.addWidget(self.txt_pass)
        l_ct.addLayout(cred_row)

        left_layout.addWidget(card_target)

        # --- Card 2: Multi-Capture Selection (Renamed to 'MULTI-CAPTURE') ---
        card_pages = QFrame()
        card_pages.setObjectName("card")
        l_cp = QVBoxLayout(card_pages)
        l_cp.setContentsMargins(14, 10, 14, 10)
        l_cp.setSpacing(6)

        h_cp_head = QHBoxLayout()
        lbl_sec2 = QLabel("2. MULTI-CAPTURE")
        lbl_sec2.setObjectName("sectionTitle")
        h_cp_head.addWidget(lbl_sec2)
        h_cp_head.addStretch()

        btn_preset = QPushButton("⭐ Standard 3 NOC")
        btn_preset.setObjectName("btn_preset")
        btn_preset.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_preset.clicked.connect(self.set_default_3_pages)
        h_cp_head.addWidget(btn_preset)

        btn_clear = QPushButton("🗑️ Reset")
        btn_clear.setObjectName("btn_clear_pages")
        btn_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_clear.clicked.connect(self.clear_all_pages)
        h_cp_head.addWidget(btn_clear)
        l_cp.addLayout(h_cp_head)

        # Chips Container
        self.page_chips_box = QVBoxLayout()
        self.page_chips_box.setSpacing(4)
        l_cp.addLayout(self.page_chips_box)

        lbl_tip = QLabel("💡 Use the navigator on the right, then click '➕ Add to Target' for other pages.")
        lbl_tip.setObjectName("brandSubtitle")
        lbl_tip.setWordWrap(True)
        l_cp.addWidget(lbl_tip)

        left_layout.addWidget(card_pages)

        # --- Card 3: Action Buttons & Progress ---
        card_action = QFrame()
        card_action.setObjectName("card")
        l_ca = QVBoxLayout(card_action)
        l_ca.setContentsMargins(14, 10, 14, 10)
        l_ca.setSpacing(6)

        self.btn_capture_single = QPushButton("📸 Capture This Site (3 Photos)")
        self.btn_capture_single.setObjectName("accentBtn")
        self.btn_capture_single.setMinimumHeight(42)
        self.btn_capture_single.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_capture_single.clicked.connect(self.start_single_capture)
        l_ca.addWidget(self.btn_capture_single)

        self.btn_capture_batch = QPushButton("⚡ Batch Capture All Sites (File)")
        self.btn_capture_batch.setMinimumHeight(36)
        self.btn_capture_batch.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_capture_batch.clicked.connect(self.start_batch_capture)
        l_ca.addWidget(self.btn_capture_batch)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - Ready")
        self.progress_bar.setMinimumHeight(26)
        l_ca.addWidget(self.progress_bar)

        left_layout.addWidget(card_action)
        left_layout.addStretch()

        left_panel.setFixedWidth(410)
        content_splitter.addWidget(left_panel)

        # ================= RIGHT COLUMN: NAVIGATOR & WORKSPACE =================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # --- Card 4: Authentic Comtech Navigation Card ---
        card_comtech = QFrame()
        card_comtech.setObjectName("card")
        l_cc = QVBoxLayout(card_comtech)
        l_cc.setContentsMargins(14, 8, 14, 8)
        l_cc.setSpacing(5)

        h_cc_head = QHBoxLayout()
        lbl_cc_title = QLabel("COMTECH MODEM WEB NAVIGATOR (MATCHES MODEM WEB INTERFACE)")
        lbl_cc_title.setObjectName("sectionTitle")
        h_cc_head.addWidget(lbl_cc_title)
        h_cc_head.addStretch()

        self.btn_add_nav_page = QPushButton("➕ Add to Target")
        self.btn_add_nav_page.setObjectName("btn_add_target")
        self.btn_add_nav_page.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add_nav_page.clicked.connect(self.add_current_nav_page)
        h_cc_head.addWidget(self.btn_add_nav_page)
        l_cc.addLayout(h_cc_head)

        # Authentic Comtech Nav Bar
        self.comtech_nav = ComtechNavBar(theme_name=self.current_theme)
        self.comtech_nav.page_selected.connect(self.on_nav_page_selected)
        l_cc.addWidget(self.comtech_nav)

        self.lbl_browsing_page = QLabel("Selected: Configuration > WAN > Mod > DPC > Commission (commission.htm)")
        self.lbl_browsing_page.setObjectName("breadcrumbText")
        self.lbl_browsing_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l_cc.addWidget(self.lbl_browsing_page)

        right_layout.addWidget(card_comtech)

        # --- Card 5: Tabs Workspace ---
        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")

        # TAB 1: Preview Gallery
        tab_view = QWidget()
        l_tv = QVBoxLayout(tab_view)
        l_tv.setContentsMargins(8, 8, 8, 8)
        l_tv.setSpacing(6)

        self.scroll_preview = QScrollArea()
        self.scroll_preview.setWidgetResizable(True)
        self.lbl_preview = QLabel("No screenshot captured yet.\nSelect a target and click '📸 Capture' to preview here.")
        self.lbl_preview.setObjectName("lbl_placeholder")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_preview.setWidget(self.lbl_preview)
        l_tv.addWidget(self.scroll_preview)

        # Gallery Control Toolbar (Removed 'Format: Full Layout...' per user request)
        h_pv_bot = QHBoxLayout()
        h_pv_bot.setSpacing(8)

        self.btn_prev_img = QPushButton("◀ Previous")
        self.btn_prev_img.clicked.connect(self.show_prev_image)
        h_pv_bot.addWidget(self.btn_prev_img)

        self.lbl_img_counter = QLabel("0 / 0 Photos")
        self.lbl_img_counter.setStyleSheet("font-weight: bold; padding: 0 6px;")
        h_pv_bot.addWidget(self.lbl_img_counter)

        self.btn_next_img = QPushButton("Next ▶")
        self.btn_next_img.clicked.connect(self.show_next_image)
        h_pv_bot.addWidget(self.btn_next_img)

        h_pv_bot.addStretch()

        btn_open_site_folder = QPushButton("📁 Current Site Folder")
        btn_open_site_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open_site_folder.clicked.connect(self.open_current_site_folder)
        h_pv_bot.addWidget(btn_open_site_folder)

        btn_open_win_img = QPushButton("🖼️ Open in Windows")
        btn_open_win_img.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open_win_img.clicked.connect(self.open_current_image)
        h_pv_bot.addWidget(btn_open_win_img)
        l_tv.addLayout(h_pv_bot)

        self.main_tabs.addTab(tab_view, "🖼️ Screenshot Preview")

        # TAB 2: Batch Sitelist Table (Only enabled in Batch Import mode)
        tab_tbl = QWidget()
        l_tbl = QVBoxLayout(tab_tbl)
        l_tbl.setContentsMargins(8, 8, 8, 8)

        self.table_sites = QTableWidget(0, 5)
        self.table_sites.setHorizontalHeaderLabels(["No", "Site ID", "Site Name", "Target IP", "Capture Status"])
        self.table_sites.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_sites.horizontalHeader().setStretchLastSection(True)
        self.table_sites.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        l_tbl.addWidget(self.table_sites)

        self.main_tabs.addTab(tab_tbl, "📋 Imported Sitelist")

        # TAB 3: Activity Log
        tab_log = QWidget()
        l_log = QVBoxLayout(tab_log)
        l_log.setContentsMargins(8, 8, 8, 8)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        l_log.addWidget(self.txt_log)

        self.main_tabs.addTab(tab_log, "📜 Activity Log")

        right_layout.addWidget(self.main_tabs)
        content_splitter.addWidget(right_panel)

        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(content_splitter, 1)

        self.render_target_page_chips()
        self.on_site_selected()
        self.on_mode_changed()
        self.log("NOC Tools - Comtech Modem Capture (VPN Active) ready.")
        self.log(f"Site Package 11 Database active. Storage: 1 Site ID = 1 Dedicated Folder in Downloads/Capture Modem/<date>/<Site ID>/")

    # ================= THEME ENGINE =================
    def apply_theme(self, theme_name: str):
        self.current_theme = theme_name
        self.theme_selector.light_button.setChecked(theme_name == LIGHT_THEME)
        self.theme_selector.dark_button.setChecked(theme_name == DARK_THEME)
        self.comtech_nav.set_theme(theme_name)
        
        theme = THEMES[theme_name]
        is_dark = (theme_name == DARK_THEME)

        app = QApplication.instance()
        if app:
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor(theme["app_bg"]))
            pal.setColor(QPalette.ColorRole.WindowText, QColor(theme["text"]))
            pal.setColor(QPalette.ColorRole.Base, QColor(theme["card_bg"]))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme["card_alt"]))
            pal.setColor(QPalette.ColorRole.Text, QColor(theme["text"]))
            pal.setColor(QPalette.ColorRole.Button, QColor(theme["card_alt"]))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor(theme["text"]))
            pal.setColor(QPalette.ColorRole.Highlight, QColor(theme["accent"]))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#091526" if is_dark else "#FFFFFF"))
            app.setPalette(pal)

        base_qss = noc_brand.theme_stylesheet(theme_name)
        extra_qss = f"""
            /* Segmented Pill Tabs for Target Modes */
            QPushButton#btn_mode_db, QPushButton#btn_mode_batch, QPushButton#btn_mode_manual {{
                background-color: {theme["card_alt"]};
                color: {theme["muted"]};
                border: 1px solid {theme["border"]};
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton#btn_mode_db:checked, QPushButton#btn_mode_batch:checked, QPushButton#btn_mode_manual:checked {{
                background-color: {theme["accent"]};
                color: {"#091526" if is_dark else "#FFFFFF"};
                border: 1.5px solid {theme["accent_hover"]};
                font-weight: bold;
            }}
            QPushButton#btn_mode_db:hover:!checked, QPushButton#btn_mode_batch:hover:!checked, QPushButton#btn_mode_manual:hover:!checked {{
                background-color: {theme["card_bg"]};
                color: {theme["text"]};
                border-color: {theme["accent"]};
            }}

            #active_site_banner {{
                background-color: {theme["card_alt"]};
                border: 1px solid {theme["border"]};
                border-radius: 6px;
            }}
            #badge_sid {{
                background-color: {theme["accent"]};
                color: {"#091526" if is_dark else "#FFFFFF"};
                font-weight: 800;
                font-size: 12px;
                padding: 2px 7px;
                border-radius: 4px;
            }}
            #badge_name {{
                background-color: {theme["card_bg"]};
                color: {theme["text"]};
                font-weight: 600;
                font-size: 12px;
                padding: 2px 7px;
                border-radius: 4px;
            }}
            #badge_ip {{
                background-color: {theme["secondary"]};
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                padding: 2px 7px;
                border-radius: 4px;
            }}
            #btn_preset {{
                background-color: {theme["card_alt"]};
                color: {theme["accent"]};
                border: 1px solid {theme["border"]};
                border-radius: 5px;
                font-weight: 600;
                font-size: 11px;
                padding: 3px 8px;
            }}
            #btn_preset:hover {{ border-color: {theme["accent"]}; }}
            #btn_clear_pages {{
                background-color: {theme["card_alt"]};
                color: {theme["alert"]};
                border: 1px solid {theme["border"]};
                border-radius: 5px;
                font-weight: 600;
                font-size: 11px;
                padding: 3px 8px;
            }}
            #btn_add_target {{
                background-color: {theme["accent"]};
                color: {"#091526" if is_dark else "#FFFFFF"};
                border: none;
                border-radius: 5px;
                font-weight: 700;
                font-size: 11px;
                padding: 4px 10px;
            }}
            #btn_add_target:hover {{ background-color: {theme["accent_hover"]}; }}
            #breadcrumbText {{
                background-color: {theme["card_alt"]};
                border: 1px solid {theme["border"]};
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: 600;
                color: {theme["accent"]};
                font-size: 12px;
            }}
            #lbl_placeholder {{
                color: {theme["muted"]};
                font-size: 13px;
            }}
            QProgressBar {{
                border: 1px solid {theme["border"]};
                border-radius: 5px;
                text-align: center;
                background-color: {theme["card_alt"]};
                color: {theme["text"]};
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {theme["accent"]};
                border-radius: 4px;
            }}
            QScrollArea {{
                background-color: {theme["card_bg"]};
                border: 1px solid {theme["border"]};
                border-radius: 8px;
            }}
            QTextEdit {{
                background-color: {theme["card_bg"]};
                color: {theme["text"]};
                border: 1px solid {theme["border"]};
                border-radius: 6px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }}
            QTableWidget {{
                background-color: {theme["card_bg"]};
                color: {theme["text"]};
                gridline-color: {theme["border"]};
                border: 1px solid {theme["border"]};
            }}
            QHeaderView::section {{
                background-color: {theme["card_alt"]};
                color: {theme["text"]};
                font-weight: 700;
                border: 1px solid {theme["border"]};
                padding: 5px;
            }}
            /* Disabled Tab Styling */
            QTabBar::tab:disabled {{
                color: {theme["border"]};
                background: transparent;
            }}
        """
        self.setStyleSheet(base_qss + extra_qss)
        self.render_target_page_chips()
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        is_dark = (self.current_theme == DARK_THEME)
        paint_network_background(painter, self.rect(), is_dark=is_dark, opacity=0.50)

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{ts}] {msg}")

    # ================= TARGET PAGES MANAGEMENT =================
    def render_target_page_chips(self):
        while self.page_chips_box.count():
            item = self.page_chips_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        theme = THEMES[self.current_theme]

        if not self.selected_target_pages:
            lbl_none = QLabel("(Target list is empty! Click '➕ Add to Target' on the right)")
            lbl_none.setStyleSheet("color: #F4778C; font-style: italic; font-size: 11px;")
            self.page_chips_box.addWidget(lbl_none)
        else:
            for idx, p in enumerate(self.selected_target_pages):
                chip = QFrame()
                chip.setStyleSheet(
                    f"QFrame {{ background-color: {theme['card_alt']}; "
                    f"border: 1px solid {theme['border']}; border-radius: 6px; padding: 2px 6px; }}"
                )
                l_chip = QHBoxLayout(chip)
                l_chip.setContentsMargins(6, 2, 6, 2)
                l_chip.setSpacing(6)

                lbl_num = QLabel(f"<b>{idx+1}.</b>")
                lbl_num.setStyleSheet(f"color: {theme['accent']}; font-size: 11px;")
                l_chip.addWidget(lbl_num)

                lbl_name = QLabel(f"<b>{p['name']}</b> <span style='color:{theme['muted']};'>({p['path']})</span>")
                lbl_name.setStyleSheet(f"color: {theme['text']}; font-size: 11px;")
                l_chip.addWidget(lbl_name)
                l_chip.addStretch()

                btn_del = QPushButton("✕")
                btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_del.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        color: #F4778C;
                        font-weight: bold;
                        font-size: 12px;
                        padding: 0 4px;
                    }
                    QPushButton:hover { color: #FF2E55; }
                """)
                btn_del.clicked.connect(lambda checked, i=idx: self.remove_target_page(i))
                l_chip.addWidget(btn_del)

                self.page_chips_box.addWidget(chip)

        self.update_action_buttons_text()

    def set_default_3_pages(self):
        self.selected_target_pages = [dict(p) for p in DEFAULT_NOC_PAGES]
        self.render_target_page_chips()
        self.log("Target reset to Standard 3 NOC (Commission, DPC, Config).")

    def clear_all_pages(self):
        self.selected_target_pages = []
        self.render_target_page_chips()
        self.log("Target page list cleared.")

    def remove_target_page(self, index: int):
        if 0 <= index < len(self.selected_target_pages):
            removed = self.selected_target_pages.pop(index)
            self.render_target_page_chips()
            self.log(f"Target removed: {removed['name']} ({removed['path']})")

    def on_nav_page_selected(self, page_path: str, breadcrumb_str: str):
        self.active_page_path = page_path
        self.active_breadcrumb = breadcrumb_str
        parts = breadcrumb_str.split(" > ")
        self.active_page_name = parts[-1] if parts else page_path
        self.lbl_browsing_page.setText(f"Selected: {breadcrumb_str} ({page_path})")

    def add_current_nav_page(self):
        for p in self.selected_target_pages:
            if p["path"] == self.active_page_path:
                QMessageBox.information(self, "Info", f"Page '{p['name']}' is already in target list!")
                return

        new_item = {
            "name": self.active_page_name,
            "path": self.active_page_path,
            "breadcrumb": self.active_breadcrumb
        }
        self.selected_target_pages.append(new_item)
        self.render_target_page_chips()
        self.log(f"Target added: {new_item['name']} ({new_item['path']})")

    def update_action_buttons_text(self):
        n_pages = len(self.selected_target_pages)
        if self.btn_mode_db.isChecked() or self.btn_mode_manual.isChecked():
            self.btn_capture_single.setText(f"📸 Capture This Site ({self.current_site_id} : {n_pages} Photos)")
            self.btn_capture_batch.setText(f"⚡ Batch Capture All Sites (From File)")
        else:
            n_sites = len(self.imported_sites)
            total = n_sites * n_pages
            self.btn_capture_single.setText(f"📸 Capture Site Ini ({self.current_site_id})")
            self.btn_capture_batch.setText(f"⚡ Batch Capture ({n_sites} Sites x {n_pages} Pages = {total} Photos)")

    def update_active_badge(self):
        self.lbl_badge_sid.setText(self.current_site_id)
        self.lbl_badge_name.setText(self.current_site_name)
        self.lbl_badge_ip.setText(f"{self.current_ip}:{self.txt_port.text().strip()}")
        self.update_action_buttons_text()

    def on_mode_changed(self):
        if self.btn_mode_db.isChecked():
            self.btn_mode_db.setText("● Site Package 11")
            self.btn_mode_batch.setText("Import Sitelist (Excel/TXT)")
            self.btn_mode_manual.setText("Manual IP")
            self.stack_mode.setCurrentIndex(0)
            # Disable Batch Sitelist Tab when not in batch mode
            self.main_tabs.setTabEnabled(1, False)
            if self.main_tabs.currentIndex() == 1:
                self.main_tabs.setCurrentIndex(0)
            self.on_site_selected()
        elif self.btn_mode_batch.isChecked():
            self.btn_mode_db.setText("Site Package 11")
            self.btn_mode_batch.setText("● Import Sitelist (Excel/TXT)")
            self.btn_mode_manual.setText("Manual IP")
            self.stack_mode.setCurrentIndex(1)
            # Enable Batch Sitelist Tab only in batch mode
            self.main_tabs.setTabEnabled(1, True)
            self.main_tabs.setCurrentIndex(1)
            self.current_site_id = "BATCH_MODE"
            self.current_site_name = f"{len(self.imported_sites)} Site"
            self.current_ip = "Various IP"
            self.update_active_badge()
        else:
            self.btn_mode_db.setText("Site Package 11")
            self.btn_mode_batch.setText("Import Sitelist (Excel/TXT)")
            self.btn_mode_manual.setText("● Manual IP")
            self.stack_mode.setCurrentIndex(2)
            # Disable Batch Sitelist Tab when not in batch mode
            self.main_tabs.setTabEnabled(1, False)
            if self.main_tabs.currentIndex() == 1:
                self.main_tabs.setCurrentIndex(0)
            self.on_manual_changed()

    def on_site_selected(self):
        text = self.combo_site.currentText()
        if not text:
            return
        parts = text.split(" - ")
        if len(parts) >= 2:
            self.current_site_id = parts[0].strip()
            rest = parts[1].strip()
            if "(" in rest and ")" in rest:
                self.current_site_name = rest[:rest.find("(")].strip()
                self.current_ip = rest[rest.find("(")+1:rest.find(")")].strip()
            else:
                self.current_site_name = rest
                self.current_ip = ip_lookup.get_ip_for_site(self.current_site_id, self.site_db)
        else:
            self.current_site_id = text.strip()
            self.current_site_name = "Single Site"
            self.current_ip = ip_lookup.get_ip_for_site(self.current_site_id, self.site_db)

        self.update_active_badge()

    def on_manual_changed(self):
        self.current_site_id = self.txt_manual_sid.text().strip() or "MANUAL"
        self.current_site_name = "Manual Input"
        self.current_ip = self.txt_manual_ip.text().strip() or "10.70.1.225"
        self.update_active_badge()

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Sitelist File", "",
            "Sitelist Files (*.xlsx *.xls *.csv *.txt);;Excel Files (*.xlsx *.xls);;CSV Files (*.csv);;Text Files (*.txt);;All Files (*.*)"
        )
        if not file_path:
            return

        self.log(f"Reading sitelist file: {file_path}")
        try:
            df_imported = ip_lookup.parse_imported_sitelist_file(file_path, self.site_db)
            if df_imported.empty:
                QMessageBox.warning(self, "Warning", "No valid Site IDs found in the file!")
                return

            self.imported_sites = df_imported.to_dict('records')
            self.lbl_batch_count.setText(f"✓ {len(self.imported_sites)} site dimuat dari {Path(file_path).name}")
            self.load_batch_table(df_imported)
            self.main_tabs.setTabEnabled(1, True)
            self.main_tabs.setCurrentIndex(1)
            self.update_active_badge()
            self.log(f"Successfully loaded {len(self.imported_sites)} sites from file.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read file: {e}")
            self.log(f"Error reading file: {e}")

    def load_batch_table(self, df):
        self.table_sites.setRowCount(len(df))
        for row_idx, row in df.iterrows():
            item_no = QTableWidgetItem(str(row_idx + 1))
            item_no.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sid = QTableWidgetItem(str(row.get('Site ID', '')))
            item_name = QTableWidgetItem(str(row.get('Site Name', '')))
            item_ip = QTableWidgetItem(str(row.get('IP', '')))
            item_status = QTableWidgetItem("Pending")
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_sites.setItem(row_idx, 0, item_no)
            self.table_sites.setItem(row_idx, 1, item_sid)
            self.table_sites.setItem(row_idx, 2, item_name)
            self.table_sites.setItem(row_idx, 3, item_ip)
            self.table_sites.setItem(row_idx, 4, item_status)

    def check_ping(self):
        ip = self.current_ip if not self.btn_mode_batch.isChecked() else "10.70.1.225"
        port_str = self.txt_port.text().strip()
        port = int(port_str) if port_str.isdigit() else 80
        self.log(f"Checking connection to {ip}:{port}...")
        self.btn_ping.setEnabled(False)
        self.btn_ping.setText("⏳ Checking...")
        QApplication.processEvents()

        try:
            if hasattr(capture_engine, 'ping_modem'):
                ok, lat = capture_engine.ping_modem(ip, port)
            elif hasattr(capture_engine, 'test_tcp_connection'):
                res = capture_engine.test_tcp_connection(ip, port)
                ok = res.get("online", False)
                lat = f"{res.get('latency_ms', 0)} ms" if ok else res.get("error", "Unreachable")
            else:
                ok, lat = False, "Ping function not found"

            self.btn_ping.setEnabled(True)
            self.btn_ping.setText("📶 Test Ping")
            
            if ok:
                msg = f"Connection to {ip}:{port} succeeded! Latency: {lat}"
                QMessageBox.information(self, "Connection Status", f"✓ {msg}")
                self.log(f"SUCCESS: {msg}")
            else:
                msg = f"Unable to connect to {ip}:{port} ({lat})"
                QMessageBox.warning(self, "Connection Status", f"✗ {msg}\n\nPastikan kabel LAN terhubung dan IP segmen laptop sudah satu subnet.")
                self.log(f"FAILED: {msg}")
        except Exception as e:
            self.btn_ping.setEnabled(True)
            self.btn_ping.setText("📶 Test Ping")
            self.log(f"ERROR: Failed to check connection: {e}")
            QMessageBox.warning(self, "Connection Status", f"Failed to check connection: {e}")

    def open_downloads_folder(self):
        target_dir = Path.home() / "Downloads" / "Capture Modem"
        target_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target_dir))
        self.log(f"Opening downloads folder: {target_dir}")

    def open_current_site_folder(self):
        target_dir = get_site_capture_dir(self.current_site_id)
        os.startfile(str(target_dir))
        self.log(f"Opening site folder: {target_dir}")

    def open_current_image(self):
        if self.last_captured_images and 0 <= self.active_preview_idx < len(self.last_captured_images):
            img_path = self.last_captured_images[self.active_preview_idx]
            if os.path.exists(img_path):
                os.startfile(img_path)
                return
        QMessageBox.information(self, "Info", "No screenshots captured yet.")

    def show_prev_image(self):
        if self.last_captured_images and self.active_preview_idx > 0:
            self.active_preview_idx -= 1
            self.display_preview_image(self.last_captured_images[self.active_preview_idx])

    def show_next_image(self):
        if self.last_captured_images and self.active_preview_idx < len(self.last_captured_images) - 1:
            self.active_preview_idx += 1
            self.display_preview_image(self.last_captured_images[self.active_preview_idx])

    def display_preview_image(self, file_path: str):
        if os.path.exists(file_path):
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                target_w = self.scroll_preview.width() - 30
                target_h = int(pixmap.height() * (target_w / pixmap.width()))
                self.lbl_preview.setPixmap(pixmap.scaled(
                    target_w, target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                self.lbl_img_counter.setText(f"{self.active_preview_idx + 1} / {len(self.last_captured_images)} Photos ({Path(file_path).name})")

    def start_single_capture(self):
        if not self.selected_target_pages:
            QMessageBox.warning(self, "Warning", "Please select at least 1 target capture page first!")
            return

        site_id = self.current_site_id
        ip = self.current_ip
        if not ip or ip in ("Unknown IP", "IP Tidak Diketahui"):
            QMessageBox.warning(self, "Warning", f"Invalid IP address for Site ID {site_id}!")
            return

        tasks = [{
            "site_id": site_id,
            "ip": ip,
            "pages": [dict(p) for p in self.selected_target_pages],
            "row_idx": -1
        }]

        self.btn_capture_single.setEnabled(False)
        self.btn_capture_batch.setEnabled(False)
        self.progress_bar.setValue(5)
        self.progress_bar.setFormat(f"Processing {site_id} ({len(self.selected_target_pages)} photos)...")
        self.log(f"Starting single site capture: {site_id} ({ip}) - {len(self.selected_target_pages)} pages...")

        self.worker = CaptureWorker(tasks, self.txt_user.text().strip(), self.txt_pass.text().strip(), is_single_site=True)
        self.worker.progress_signal.connect(self.on_worker_progress)
        self.worker.item_finished_signal.connect(self.on_worker_item_finished)
        self.worker.all_finished_signal.connect(self.on_worker_all_finished)
        self.worker.start()

    def start_batch_capture(self):
        if not self.selected_target_pages:
            QMessageBox.warning(self, "Warning", "Please select at least 1 target capture page first!")
            return

        if not self.imported_sites:
            QMessageBox.warning(self, "Warning", "Please import a sitelist file first!")
            self.btn_mode_batch.setChecked(True)
            self.on_mode_changed()
            return

        tasks = []
        for idx, row in enumerate(self.imported_sites):
            sid = str(row.get('Site ID', '')).strip()
            ip = str(row.get('IP', '')).strip()
            if sid and ip and ip not in ('Unknown IP', 'IP Tidak Diketahui'):
                tasks.append({
                    "site_id": sid,
                    "ip": ip,
                    "pages": [dict(p) for p in self.selected_target_pages],
                    "row_idx": idx
                })

        if not tasks:
            QMessageBox.warning(self, "Warning", "No sites with valid IP found to capture!")
            return

        n_pages = len(self.selected_target_pages)
        total_photos = len(tasks) * n_pages
        page_names = ", ".join([p["name"] for p in self.selected_target_pages])

        msg_lines = [
            "You are about to capture screenshots for:",
            f"• Total Sites     : {len(tasks)} Sites",
            f"• Pages per Site  : {n_pages} ({page_names})",
            f"• Total Photos    : {total_photos} PNG Files",
            f"• Storage Location: 1 Site ID = 1 Dedicated Folder",
            "",
            "Proceed with batch capture?"
        ]
        confirm = QMessageBox.question(
            self, "Confirm Batch Capture", "\n".join(msg_lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.btn_capture_single.setEnabled(False)
        self.btn_capture_batch.setEnabled(False)
        self.progress_bar.setValue(0)
        self.main_tabs.setTabEnabled(1, True)
        self.main_tabs.setCurrentIndex(1)
        self.log(f"Starting batch capture for {len(tasks)} sites ({total_photos} total photos)...")

        self.worker = CaptureWorker(tasks, self.txt_user.text().strip(), self.txt_pass.text().strip(), is_single_site=False)
        self.worker.progress_signal.connect(self.on_worker_progress)
        self.worker.item_finished_signal.connect(self.on_worker_item_finished)
        self.worker.all_finished_signal.connect(self.on_worker_all_finished)
        self.worker.start()

    def on_worker_progress(self, percent: int, msg: str):
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}% - {msg}")
        self.log(msg)

    def on_worker_item_finished(self, row_idx: int, site_id: str, success: bool, result_path_or_err: str, saved_files: list):
        if row_idx >= 0 and row_idx < self.table_sites.rowCount():
            item_status = self.table_sites.item(row_idx, 4)
            if item_status:
                if success:
                    item_status.setText("✓ Completed")
                    item_status.setForeground(QColor("#2AA8F2" if self.current_theme == DARK_THEME else "#126FE8"))
                else:
                    item_status.setText(f"✗ Partial / Failed")
                    item_status.setForeground(QColor("#F4778C"))

        site_dir = get_site_capture_dir(site_id)
        if site_dir.exists():
            png_files = sorted(list(site_dir.glob("*.png")), key=os.path.getmtime, reverse=True)
            if png_files:
                self.last_captured_images = [str(f) for f in png_files]
                self.active_preview_idx = 0
                self.display_preview_image(self.last_captured_images[0])
                self.main_tabs.setCurrentIndex(0)

        if success:
            self.log(f"SUCCESS: {site_id} fully completed ({len(saved_files)} files). Saved in {site_dir}")
        else:
            self.log(f"WARNING: {site_id} status: {result_path_or_err}")

    def on_worker_all_finished(self, total_sites: int, success_sites: int, is_single_site: bool, last_dir: str, all_files: list):
        self.btn_capture_single.setEnabled(True)
        self.btn_capture_batch.setEnabled(True)
        self.progress_bar.setFormat("100% - Completed!")
        
        # Detailed notification for single capture per user request
        if is_single_site:
            file_list_str = "\n".join([f"  {i+1}. {Path(f).name}" for i, f in enumerate(all_files)]) if all_files else "  (No files)"
            detail_msg = [
                "✓ Capture Process Succeeded!",
                "",
                f"• Site ID       : {self.current_site_id} ({self.current_site_name})",
                f"• IP Modem      : {self.current_ip}:{self.txt_port.text().strip()}",
                f"• Storage Folder :",
                f"  {last_dir}",
                f"  {last_dir}",
                "",
                f"• Saved Image Files ({len(all_files)} Photos):",
                file_list_str,
                "",
                "Note: You can open the folder directly using the '📁 Current Site Folder' button."
            ]
            QMessageBox.information(self, "Capture Completed", "\n".join(detail_msg))
        else:
            # Batch notification summary
            info_lines = [
                "Batch Capture Process Completed!",
                "",
                f"• Successful: {success_sites} of {total_sites} sites.",
                f"• Structure: Each Site ID has its own folder in Downloads/Capture Modem/<date>/<Site ID>/",
                "• Each folder contains all captured photos for selected pages."
            ]
            QMessageBox.information(self, "Completed", "\n".join(info_lines))


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    win = ModemCaptureGUI()
    win.showMaximized()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
