import os
import io
import time
import glob
import zipfile
from datetime import datetime
import pandas as pd
from PIL import Image
import streamlit as st

import capture_engine
import ip_lookup
from sitemap_data import SITEMAP_CATEGORIES, ALL_PAGES

st.set_page_config(
    page_title="Capture Modem - Comtech Heights",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px 24px;
        color: white;
        margin-bottom: 20px;
    }
    .breadcrumb-box {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
</style>
""", unsafe_allow_html=True)

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

# Load Database Sitelist
@st.cache_data(ttl=60)
def get_site_db():
    return ip_lookup.load_site_mapping()

site_db = get_site_db()

# ----------------- SIDEBAR: SITE SELECTION -----------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/satellite-sending-signal.png", width=56)
    st.title("NOC Modem Capturer")
    st.caption(f"📁 Database Mapped: **{len(site_db)} Sites**")

    mode_input = st.radio("Pilih Mode Target:", ["🎯 Sitelist Satuan (Cari Site)", "📂 Import File (Excel/CSV/TXT)", "🌐 Manual IP"])

    active_ip = "10.70.1.225"
    active_site_id = "PAB0840"
    active_site_name = "PUSUTILIGUM"

    if mode_input == "🎯 Sitelist Satuan (Cari Site)":
        if not site_db.empty:
            site_options = [f"{row['Site ID']} - {row['Site Name']} ({row['IP']})" for _, row in site_db.iterrows()]
            default_idx = 0
            for i, opt in enumerate(site_options):
                if "PAB0840" in opt:
                    default_idx = i
                    break
            selected_site_str = st.selectbox("Pilih / Ketik Site ID:", site_options, index=default_idx)
            
            # Extract
            sid = selected_site_str.split(" - ")[0]
            matched = site_db[site_db["Site ID"] == sid].iloc[0]
            active_site_id = matched["Site ID"]
            active_site_name = matched["Site Name"]
            active_ip = matched["IP"]
            
            st.success(f"Site: {active_site_id} ({active_site_name}) - IP: {active_ip}")
        else:
            st.warning("Database site kosong di folder mapping Ip Modem by site id.")
            active_ip = st.text_input("IP Target", value="10.70.1.225")

    elif mode_input == "🌐 Manual IP":
        active_ip = st.text_input("IP Target", value="10.70.1.225")
        active_site_id = st.text_input("Site ID (Opsional)", value="MANUAL")
        active_site_name = "-"

    st.divider()
    st.subheader("Autentikasi & Port")
    port = st.number_input("Port HTTP", min_value=1, max_value=65535, value=80)
    username = st.text_input("Username", value="comtech")
    password = st.text_input("Password", value="comtech", type="password")

    if st.button("🔍 Cek Ping / Latensi", use_container_width=True):
        with st.spinner(f"Ping ke {active_ip}..."):
            res = capture_engine.test_tcp_connection(active_ip, int(port), timeout=3.5)
            if res["online"]:
                st.success(f"🟢 Terhubung! ({res['latency_ms']} ms)")
            else:
                st.error(f"🔴 Offline: {res['error']}")

# ----------------- TOP BANNER -----------------
st.markdown(f"""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
        <div>
            <h2 style="margin: 0; font-size: 24px;">🛰️ Comtech Heights H-Pico Web Capturer</h2>
            <p style="margin: 4px 0 0 0; color: #94a3b8; font-size: 14px;">
                Active Site: <strong style="color: #38bdf8;">{active_site_id} ({active_site_name})</strong> &nbsp;|&nbsp; 
                IP: <strong style="color: #f1f5f9;">http://{active_ip}:{port}/</strong>
            </p>
        </div>
        <div style="margin-top: 8px;">
            <span style="background:#065f46; color:#34d399; padding:4px 10px; border-radius:20px; font-weight:600; font-size:12px;">IP MAPPED</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ----------------- TABS -----------------
tab1, tab2, tab3 = st.tabs([
    "🧭 Navigasi Menu Comtech (Persis Gambar)",
    "📂 Batch Import Sitelist (Excel/CSV/TXT)",
    "🖼️ Galeri Hasil Capture"
])

# ================= TAB 1: MODEM NAVIGATION EXACT CLONE =================
with tab1:
    st.markdown("### Navigasi Tab Menu (Klik Seperti Pada Modem Asli)")
    st.caption("Pilih navigasi bertingkat berikut untuk langsung menangkap layar halaman tersebut secara utuh (Header VFP + Menu + Form).")

    # Breadcrumb Selection Structure
    l1_col, l2_col, l3_col, l4_col, l5_col = st.columns(5)
    
    with l1_col:
        l1 = st.selectbox("Menu Utama", ["Configuration", "Home", "Admin", "Status", "Utility"])

    selected_page_path = "home.htm"
    selected_page_title = "H-Pico Home"

    if l1 == "Home":
        with l2_col:
            l2 = st.selectbox("Sub Menu", ["Home", "Contact"])
        if l2 == "Home":
            selected_page_path, selected_page_title = "home.htm", "H-Pico Home"
        else:
            selected_page_path, selected_page_title = "contact.htm", "Support & Contact"

    elif l1 == "Admin":
        with l2_col:
            l2 = st.selectbox("Sub Menu", ["Access", "License", "Auto Logout"])
        if l2 == "Access":
            selected_page_path, selected_page_title = "admin_access.htm", "Admin Access"
        elif l2 == "License":
            selected_page_path, selected_page_title = "license.htm", "FAST License"
        else:
            selected_page_path, selected_page_title = "alogout.htm", "Auto Logout"

    elif l1 == "Configuration":
        with l2_col:
            l2 = st.selectbox("Interface / WAN", ["WAN", "Interface", "Network", "ECM", "MEO", "Roaming"])
        
        if l2 == "Interface":
            with l3_col:
                l3 = st.selectbox("Port", ["GE (Gigabit Ethernet)", "Mgmt (FastEthernet)"])
            if "GE" in l3:
                selected_page_path, selected_page_title = "ge1.htm", "Port Configuration (GE)"
            else:
                selected_page_path, selected_page_title = "femgt.htm", "Management FE"

        elif l2 == "WAN":
            with l3_col:
                l3 = st.selectbox("RF Mod/Demod", ["Mod", "Demod", "QoS", "Compression", "BUC", "LNB", "WANOp"])
            
            if l3 == "Mod":
                with l4_col:
                    l4 = st.selectbox("Mod Config", ["DPC", "Config", "ACM"])
                if l4 == "DPC":
                    with l5_col:
                        l5 = st.selectbox("DPC Sub", ["Commission", "DPC"])
                    if l5 == "Commission":
                        selected_page_path, selected_page_title = "commission.htm", "Modem Commissioning"
                    else:
                        selected_page_path, selected_page_title = "dpc.htm", "Tx Dynamic Power Control"
                elif l4 == "Config":
                    selected_page_path, selected_page_title = "mod.htm", "Modulator Config"
                else:
                    selected_page_path, selected_page_title = "acm.htm", "ACM Configuration"
            elif l3 == "Demod":
                selected_page_path, selected_page_title = "tuner1.htm", "Demodulator / Tuner"
            elif l3 == "BUC":
                selected_page_path, selected_page_title = "buc.htm", "BUC Details"
            elif l3 == "LNB":
                selected_page_path, selected_page_title = "lnb.htm", "LNB Details"
            elif l3 == "WANOp":
                selected_page_path, selected_page_title = "wanop.htm", "WAN Optimization"
            elif l3 == "QoS":
                selected_page_path, selected_page_title = "ip_wan.htm", "QoS Configuration"
            else:
                selected_page_path, selected_page_title = "ip_compression.htm", "IP Compression"

        elif l2 == "Network":
            with l3_col:
                l3 = st.selectbox("Routing", ["Routing Table", "DHCP", "IGMP", "ARP"])
            if l3 == "Routing Table":
                selected_page_path, selected_page_title = "ip_routing.htm", "IP Routing Table"
            elif l3 == "DHCP":
                selected_page_path, selected_page_title = "ip_routing_dhcp.htm", "DHCP Server"
            elif l3 == "IGMP":
                selected_page_path, selected_page_title = "ip_routing_igmp.htm", "IGMP Multicast"
            else:
                selected_page_path, selected_page_title = "ip_lan_arp.htm", "ARP Table"
        elif l2 == "ECM":
            selected_page_path, selected_page_title = "ecm.htm", "ECM"
        elif l2 == "MEO":
            selected_page_path, selected_page_title = "meo.htm", "MEO Tracking"
        else:
            selected_page_path, selected_page_title = "roaming.htm", "IP Roaming"

    elif l1 == "Status":
        with l2_col:
            l2 = st.selectbox("Category", ["Monitor", "Statistics"])
        if l2 == "Monitor":
            with l3_col:
                l3 = st.selectbox("Tool", ["Alarms", "Events", "Spectrum", "Constellation Graph"])
            if l3 == "Alarms":
                selected_page_path, selected_page_title = "alarms.htm", "Active & Stored Alarms"
            elif l3 == "Events":
                selected_page_path, selected_page_title = "event.htm", "Event Log Monitor"
            elif l3 == "Spectrum":
                selected_page_path, selected_page_title = "spectrum.htm", "Rx Spectrum Graph"
            else:
                selected_page_path, selected_page_title = "graph.htm", "Constellation Graph"
        else:
            with l3_col:
                l3 = st.selectbox("Stats", ["Ethernet", "Transmission", "Switch Traffic", "WANOp Stats"])
            if l3 == "Ethernet":
                selected_page_path, selected_page_title = "ether_stats.htm", "Ethernet Statistics"
            elif l3 == "Transmission":
                selected_page_path, selected_page_title = "stats.htm", "Transmission Statistics"
            elif l3 == "Switch Traffic":
                selected_page_path, selected_page_title = "bridgingstats.htm", "Managed Switch Stats"
            else:
                selected_page_path, selected_page_title = "wanop_stats.htm", "WANOp Statistics"

    else: # Utility
        with l2_col:
            l2 = st.selectbox("Utility Type", ["Save", "Firmware", "Reboot", "SNMP", "NMS"])
        if l2 == "Save":
            selected_page_path, selected_page_title = "save.htm", "Save Configuration"
        elif l2 == "Firmware":
            selected_page_path, selected_page_title = "firmware.htm", "Firmware Management"
        elif l2 == "Reboot":
            selected_page_path, selected_page_title = "reboot.htm", "Reboot Modem"
        elif l2 == "SNMP":
            selected_page_path, selected_page_title = "snmp.htm", "SNMP Config"
        else:
            selected_page_path, selected_page_title = "nms.htm", "NMS Connection"

    # Display simulated breadcrumb box exactly like Comtech
    st.markdown(f"""
    <div class="breadcrumb-box">
        <span style="color: #64748b; font-size: 13px;">Navigasi Terpilih:</span><br>
        <span style="font-size: 16px; font-weight: 600; color: #0f172a;">
            {l1} &nbsp;&gt;&nbsp; {selected_page_title}
        </span>
        <span style="margin-left: 12px; background: #e2e8f0; color: #334155; padding: 2px 8px; border-radius: 4px; font-family: monospace; font-size: 13px;">
            {selected_page_path}
        </span>
    </div>
    """, unsafe_allow_html=True)

    btn_cap, _ = st.columns([1, 2])
    with btn_cap:
        trigger_capture = st.button(f"📸 Capture Halaman {selected_page_title}", type="primary", use_container_width=True)

    if trigger_capture:
        clean_name = f"{active_site_id}_{selected_page_path.replace('.htm', '')}"
        out_file = os.path.join(CAPTURES_DIR, f"{clean_name}.png")
        
        with st.spinner(f"Mengambil tangkapan layar {selected_page_title} dari {active_site_id} ({active_ip})..."):
            res = capture_engine.capture_page(
                host=active_ip,
                page_path=selected_page_path,
                username=username,
                password=password,
                output_path=out_file
            )
            if res.get("success"):
                st.success(f"✅ Berhasil! Disimpan sebagai: {os.path.basename(out_file)}")
                st.image(out_file, caption=f"{active_site_id} - {selected_page_title} (Full Layout)", use_container_width=True)
                with open(out_file, "rb") as f:
                    st.download_button("📥 Unduh PNG", f, file_name=f"{clean_name}.png", mime="image/png")
            else:
                st.error(f"Gagal capture: {res.get('error')}")

# ================= TAB 2: IMPORT BATCH SITELIST =================
with tab2:
    st.subheader("Import File Sitelist (Excel, CSV, atau TXT)")
    st.write("Unggah file berisi daftar Site ID. Sistem akan otomatis mencocokkan setiap Site ID dengan IP Modem dari folder `mapping Ip Modem by site id`.")

    uploaded_file = st.file_uploader("Pilih File Sitelist (.xlsx, .xls, .csv, .txt)", type=["xlsx", "xls", "csv", "txt"])

    if uploaded_file:
        parsed_sites = []
        try:
            if uploaded_file.name.endswith((".xlsx", ".xls")):
                in_df = pd.read_excel(uploaded_file)
                for col in in_df.columns:
                    if "site" in str(col).lower():
                        parsed_sites = in_df[col].dropna().astype(str).str.strip().tolist()
                        break
                if not parsed_sites:
                    parsed_sites = in_df.iloc[:, 0].dropna().astype(str).str.strip().tolist()

            elif uploaded_file.name.endswith(".csv"):
                in_df = pd.read_csv(uploaded_file)
                for col in in_df.columns:
                    if "site" in str(col).lower():
                        parsed_sites = in_df[col].dropna().astype(str).str.strip().tolist()
                        break
                if not parsed_sites:
                    parsed_sites = in_df.iloc[:, 0].dropna().astype(str).str.strip().tolist()

            else: # TXT
                content = uploaded_file.read().decode("utf-8", errors="ignore")
                parsed_sites = [line.strip() for line in content.splitlines() if line.strip()]

            st.info(f"Ditemukan **{len(parsed_sites)} item** dari file `{uploaded_file.name}`.")

            # Match with database
            results = []
            for s in parsed_sites:
                match = ip_lookup.lookup_site(s, site_db)
                if match:
                    results.append({
                        "Site ID Input": s,
                        "Matched Site ID": match["Site ID"],
                        "Site Name": match["Site Name"],
                        "IP Modem": match["IP"],
                        "Status": "Mapped"
                    })
                else:
                    results.append({
                        "Site ID Input": s,
                        "Matched Site ID": "-",
                        "Site Name": "-",
                        "IP Modem": "Tidak Ditemukan",
                        "Status": "Not Found"
                    })

            batch_df = pd.DataFrame(results)
            st.dataframe(batch_df, use_container_width=True)

            mapped_count = len(batch_df[batch_df["Status"] == "Mapped"])
            st.write(f"Siap diproses: **{mapped_count} dari {len(batch_df)} sites** terpetakan ke IP.")

            col_bp1, col_bp2 = st.columns([2, 1])
            with col_bp1:
                batch_page_to_capture = st.selectbox(
                    "Pilih Halaman yang Akan Di-capture untuk Semua Site:",
                    ["commission.htm (Commissioning / BUC / Power)", "ge1.htm (Port Configuration)", "alarms.htm (Alarms)", "home.htm (Home)", "stats.htm (Transmission Stats)"]
                )
                b_path = batch_page_to_capture.split(" ")[0]

            with col_bp2:
                start_batch = st.button("⚡ Mulai Batch Capture Semua Site", type="primary", use_container_width=True)

            if start_batch:
                mapped_rows = batch_df[batch_df["Status"] == "Mapped"].to_dict("records")
                p_bar = st.progress(0)
                status_txt = st.empty()

                for idx, r in enumerate(mapped_rows):
                    s_id = r["Matched Site ID"]
                    s_ip = r["IP Modem"]
                    status_txt.text(f"Mengambil capture ({idx+1}/{len(mapped_rows)}): Site {s_id} ({s_ip})...")

                    out_path = os.path.join(CAPTURES_DIR, f"{s_id}_{b_path.replace('.htm', '')}.png")
                    capture_engine.capture_page(
                        host=s_ip,
                        page_path=b_path,
                        username=username,
                        password=password,
                        output_path=out_path
                    )
                    p_bar.progress((idx + 1) / len(mapped_rows))

                status_txt.text("Semua batch capture selesai!")
                st.success(f"Berhasil menangkap {len(mapped_rows)} gambar!")
                st.rerun()

        except Exception as e:
            st.error(f"Gagal memproses file: {e}")

# ================= TAB 3: GALLERY =================
with tab3:
    st.subheader("Galeri Tangkapan Layar Lengkap")
    
    files = sorted(glob.glob(os.path.join(CAPTURES_DIR, "*.png")), key=os.path.getmtime, reverse=True)
    
    col_gh, col_ga = st.columns([3, 1])
    with col_gh:
        st.write(f"Total screenshot tersimpan: **{len(files)} file**")
    with col_ga:
        if files:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                for f in files:
                    zf.write(f, arcname=os.path.basename(f))
            buf.seek(0)
            st.download_button("📦 Download Semua (ZIP)", buf, file_name="captures_all.zip", mime="application/zip", use_container_width=True)

    if not files:
        st.info("Belum ada hasil capture tersimpan.")
    else:
        g_cols = st.columns(2)
        for i, fpath in enumerate(files):
            fname = os.path.basename(fpath)
            fsize_kb = round(os.path.getsize(fpath) / 1024, 1)
            with g_cols[i % 2]:
                st.image(fpath, caption=f"{fname} ({fsize_kb} KB)", use_container_width=True)
                with open(fpath, "rb") as fb:
                    st.download_button(f"⬇️ Download {fname}", fb, file_name=fname, mime="image/png", key=f"d_{fname}", use_container_width=True)
                st.divider()
