# Capture_Modem: Comtech Heights H-Pico Web Mapper & Capturer

Aplikasi Python berbasis **Streamlit** dan **Playwright** untuk melakukan mapping struktur halaman web dan capture screenshot otomatis pada perangkat **Comtech EF Data Heights H-Pico Remote Gateway** (atau perangkat jaringan lainnya) dengan **tampilan penuh (Header VFP + Menu + Konten tanpa terpotong)**.

---

## 🛰️ Hasil Mapping Target (10.70.1.225)

- **Target Device:** Comtech Heights H-Pico (Model Remote Gateway)
- **Unit ID:** `PAB0840_PUSUTILIGUM`
- **Firmware Version:** `4.4.5`
- **Metode Autentikasi:** HTTP Digest Authentication (`comtech:comtech`)
- **Total Endpoint Ditemukan:** **69 Halaman**

### Kategori Halaman yang Dipetakan:
1. **🏠 Overview & Home:**
   - `home.htm`: Beranda utama
   - `vfpHeights.htm`: Virtual Front Panel (VFP) real-time
   - `features.htm`: Kapabilitas lisensi perangkat
   - `contact.htm`: Kontak dukungan teknis
2. **🛰️ RF & Satellite Modem:**
   - `mod.htm`: Modulator (Frekuensi Tx, Symbol Rate, MODCOD, Daya Tx)
   - `tuner1.htm`: Demodulator / Tuner Rx
   - `acm.htm` / `rx_acm.htm` / `acm-details.htm`: Adaptive Coding & Modulation
   - `buc.htm`: Block Upconverter (Daya 24/48V, 10 MHz reference)
   - `lnb.htm`: Low-Noise Block downconverter (Daya DC, LO)
   - `carrierid.htm`: Carrier ID (CID)
   - `dpc.htm`: Dynamic Power Control
   - `commission.htm`: Mode komisioning & pointing antena
   - `workingmode.htm`: Router Mode vs Bridge/BPM Mode
   - `meo.htm`: MEO satellite tracking
3. **📊 Status, Alarms & Spectrum:**
   - `alarms.htm`: Alarm aktif & riwayat gangguan
   - `event.htm`: Event log monitor
   - `spectrum.htm`: Rx Spectrum Analyzer grafik
   - `graph.htm`: Constellation Diagram (I/Q)
   - `stats.htm` / `ether_stats.htm`: Statistik transmisi & port Ethernet
   - `bridgingstats.htm` / `bridgingstats_lan.htm`: Throughput switch
   - `wanop_stats.htm`: Akselerasi WAN optimization
   - `pp_status_trafficstats_qos.htm` / `pp_status_trafficstats_compression.htm`
4. **🌐 IP Networking & Routing:**
   - `femgt.htm`: FastEthernet Management IP
   - `ge1.htm`: Gigabit Ethernet data port
   - `ip_routing.htm` / `ip_routing_dhcp.htm` / `ip_routing_igmp.htm`
   - `ip_lan_arp.htm`: ARP Table Cache
   - `ip_wan.htm` / `ip_wan_label.htm`: QoS queuing & VLAN tagging
   - `ip_compression.htm` / `wanop.htm`: Kompresi paket & TCP PeP
5. **🛠️ Admin & Utilities:**
   - `save.htm`: Simpan konfigurasi ke NVRAM
   - `admin_access.htm` / `alogout.htm`: Manajemen akun & timeout
   - `firmware.htm`: Dual-bank firmware image
   - `license.htm`: FAST Feature License
   - `snmp.htm` / `nms.htm`: SNMP & NetVue NMS
   - `reboot.htm`: Reboot sistem

---

## 🚀 Cara Menjalankan Aplikasi

### Cara 1: Menggunakan File Batch (Paling Praktis)
Cukup klik ganda (double-click) file:
`run_app.bat`

### Cara 2: Lewat Terminal / PowerShell
```powershell
cd Capture_Modem
python -m streamlit run app.py
```

Aplikasi dapat diakses di browser pada:
👉 **http://localhost:8501**

---

## 📁 Struktur File Proyek

```text
Capture_Modem/
├── app.py                 # Antarmuka Dashboard Web Streamlit
├── capture_engine.py      # Engine Playwright Headless Edge & Font Antialiasing
├── sitemap_data.py        # Registri metadata 69 halaman terpetakan
├── crawler.py             # Script deep crawler & discovery
├── map_all.py             # Script pemetaan relasi antar menu
├── mapped_structure.json  # Data JSON lengkap seluruh 69 endpoint
├── requirements.txt       # Daftar pustaka Python yang dibutuhkan
├── run_app.bat            # Script pintasan untuk menjalankan aplikasi
└── captures/              # Folder penyimpanan hasil screenshot PNG
```
