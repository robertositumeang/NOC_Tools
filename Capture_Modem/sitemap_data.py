"""
Comtech Heights H-Pico Remote Gateway - Sitemap & Page Registry
Extracted and categorized from target 10.70.1.225
"""

SITEMAP_CATEGORIES = {
    "🏠 Overview & Home": {
        "description": "Halaman beranda, identitas unit, dan navigasi utama sistem",
        "icon": "🏠",
        "pages": [
            {"path": "home.htm", "title": "H-Pico Home", "desc": "Halaman beranda utama dengan menu navigasi perangkat"},
            {"path": "main.htm", "title": "Main Frameset", "desc": "Struktur frame utama penggabung VFP dan konten"},
            {"path": "vfpHeights.htm", "title": "Virtual Front Panel (VFP)", "desc": "Panel status real-time modem (RF, Tx, Rx, Es/No, RSL)"},
            {"path": "features.htm", "title": "Modem Features", "desc": "Daftar fitur, lisensi software, dan kapabilitas terpasang"},
            {"path": "contact.htm", "title": "Support & Contact", "desc": "Informasi kontak pabrikan Comtech EF Data"}
        ]
    },
    "🛰️ RF & Satellite Modem": {
        "description": "Konfigurasi frekuensi, modulasi, demodulator, BUC, LNB, dan parameter satelit",
        "icon": "🛰️",
        "pages": [
            {"path": "mod.htm", "title": "Modulator", "desc": "Pengaturan Tx Modulator: frekuensi, symbol rate, daya Tx, MODCOD"},
            {"path": "tuner1.htm", "title": "Demodulator / Tuner", "desc": "Pengaturan Rx Demodulator: frekuensi Rx, symbol rate, tracking"},
            {"path": "acm.htm", "title": "Adaptive Coding & Modulation (ACM)", "desc": "Pengaturan adaptasi modulasi dan coding otomatis"},
            {"path": "rx_acm.htm", "title": "Rx ACM Parameters", "desc": "Parameter batas SNR dan transisi ACM pada receiver"},
            {"path": "acm-details.htm", "title": "ACM Details & Constellation", "desc": "Statistik performa dan level modulasi aktif ACM"},
            {"path": "buc.htm", "title": "Block Upconverter (BUC)", "desc": "Kontrol daya BUC (24V/48V), 10 MHz reference oscillator, LO"},
            {"path": "lnb.htm", "title": "Low-Noise Block (LNB)", "desc": "Kontrol daya LNB (13V/18V DC), 10 MHz reference, LO frequency"},
            {"path": "carrierid.htm", "title": "Carrier ID (CID)", "desc": "Pengaturan ETSI Carrier Identification untuk koordinasi satelit"},
            {"path": "dpc.htm", "title": "Dynamic Power Control (DPC)", "desc": "Kompensasi daya uplink otomatis berdasarkan kondisi link"},
            {"path": "commission.htm", "title": "Modem Commissioning", "desc": "Mode pointing antena dan kalibrasi instalasi"},
            {"path": "workingmode.htm", "title": "Working Mode", "desc": "Mode operasi modem (Router Mode vs Bridge/BPM Mode)"},
            {"path": "meo.htm", "title": "MEO Satellite Tracking", "desc": "Konfigurasi tracking konstelasi satelit Medium Earth Orbit"}
        ]
    },
    "📊 Status, Alarms & Spectrum": {
        "description": "Grafik spektrum, konstelasi sinyal, alarm aktif, dan statistik transmisi",
        "icon": "📊",
        "pages": [
            {"path": "alarms.htm", "title": "Active & Stored Alarms", "desc": "Daftar alarm aktif perangkat, riwayat kesalahan, dan event"},
            {"path": "event.htm", "title": "Event Log Monitor", "desc": "Log peristiwa sistem modem dan perubahan status jaringan"},
            {"path": "spectrum.htm", "title": "Rx Spectrum Analyzer", "desc": "Grafik spektrum frekuensi Rx real-time dari sinyal satelit"},
            {"path": "graph.htm", "title": "Constellation Diagram", "desc": "Diagram konstelasi I/Q (QPSK, 8-ARY, 16-APSK) dan kualitas sinyal"},
            {"path": "stats.htm", "title": "Transmission Statistics", "desc": "Statistik paket TX/RX, bit error rate (BER), error frames"},
            {"path": "ether_stats.htm", "title": "Ethernet Statistics", "desc": "Statistik port Ethernet fisik (Tx/Rx bytes, packets, drops)"},
            {"path": "bridgingstats.htm", "title": "Managed Switch Traffic Stats", "desc": "Statistik throughput switch internal perangkat"},
            {"path": "bridgingstats_lan.htm", "title": "Managed Switch LAN Stats", "desc": "Statistik port switch sisi jaringan lokal (LAN)"},
            {"path": "wanop_stats.htm", "title": "WANOp Statistics", "desc": "Statistik akselerasi WAN Optimization dan penghematan bandwidth"},
            {"path": "pp_status_trafficstats_router.htm", "title": "Router Traffic Stats", "desc": "Statistik paket per interface routing"},
            {"path": "pp_status_trafficstats_qos.htm", "title": "QoS Traffic Stats", "desc": "Statistik per antrian antarmuka QoS dan prioritas trafik"},
            {"path": "pp_status_trafficstats_compression.htm", "title": "Compression Stats", "desc": "Rasio kompresi data dan header packet IP"},
            {"path": "ptpstats.htm", "title": "PTP Clock Statistics", "desc": "Statistik jitter, offset waktu, dan sinkronisasi IEEE 1588"}
        ]
    },
    "🌐 IP Networking & Routing": {
        "description": "Pengaturan antarmuka jaringan, routing IP, DHCP, QoS, VLAN, dan akselerasi WAN",
        "icon": "🌐",
        "pages": [
            {"path": "femgt.htm", "title": "FastEthernet Management (FE)", "desc": "Alamat IP, subnet mask, dan konfigurasi port manajemen FE"},
            {"path": "ge1.htm", "title": "Gigabit Ethernet (GE1)", "desc": "Konfigurasi antarmuka Gigabit Ethernet untuk trafik data"},
            {"path": "ip_routing.htm", "title": "IP Routing Table", "desc": "Tabel rute statis, default gateway, dan metric antarmuka"},
            {"path": "ip_routing_dhcp.htm", "title": "DHCP Server & Relay", "desc": "Konfigurasi scope IP DHCP untuk client lokal"},
            {"path": "ip_routing_igmp.htm", "title": "IGMP Multicast", "desc": "Pengaturan IGMP proxy dan forwarding multicast over satellite"},
            {"path": "ip_lan_arp.htm", "title": "ARP Table Cache", "desc": "Daftar pemetaan IP ke MAC address perangkat lokal terhubung"},
            {"path": "ip_wan.htm", "title": "WAN QoS & Classification", "desc": "Pengaturan aturan QoS, DiffServ DSCP, dan alokasi antrian"},
            {"path": "ip_wan_label.htm", "title": "VLAN & Flow Labeling", "desc": "Pengaturan tag 802.1Q VLAN dan pemetaan port"},
            {"path": "ip_compression.htm", "title": "IP Packet Compression", "desc": "Algoritma kompresi header TCP/IP dan kompresi payload"},
            {"path": "wanop.htm", "title": "WAN Optimization (WANOp)", "desc": "Mesin TCP PeP, SCPS, dan akselerasi protokol latensi tinggi"},
            {"path": "roaming.htm", "title": "IP Roaming", "desc": "Konfigurasi mobilitas roaming antar beam satelit"},
            {"path": "ptp.htm", "title": "Precision Time Protocol (PTP)", "desc": "Pengaturan sinkronisasi waktu presisi tinggi IEEE 1588v2"}
        ]
    },
    "🛠️ Admin & System Utilities": {
        "description": "Manajemen firmware, lisensi, user akun, SNMP, backup konfigurasi, dan reboot",
        "icon": "🛠️",
        "pages": [
            {"path": "save.htm", "title": "Save Configuration & Factory", "desc": "Menyimpan konfigurasi ke NVRAM atau reset ke default"},
            {"path": "admin_access.htm", "title": "Admin Access & Security", "desc": "Manajemen hak akses pengguna (user/admin/super)"},
            {"path": "alogout.htm", "title": "Auto Logout Timer", "desc": "Pengaturan durasi timeout otomatis sesi web GUI"},
            {"path": "firmware.htm", "title": "Firmware Management", "desc": "Dual-bank image firmware, upload, dan pemilihan boot image"},
            {"path": "license.htm", "title": "FAST Feature License", "desc": "Input kode lisensi FAST Comtech untuk unlock fitur modem"},
            {"path": "snmp.htm", "title": "SNMP Management", "desc": "Konfigurasi SNMP v1/v2c/v3, trap destination, dan community"},
            {"path": "nms.htm", "title": "NMS Connection", "desc": "Pengaturan koneksi ke sistem sentral Comtech NetVue/NMS"},
            {"path": "reboot.htm", "title": "Reboot System", "desc": "Perintah soft restart modem dan reload perangkat lunak"}
        ]
    }
}

ALL_PAGES = []
for cat_name, cat_data in SITEMAP_CATEGORIES.items():
    for p in cat_data["pages"]:
        ALL_PAGES.append({**p, "category": cat_name})
