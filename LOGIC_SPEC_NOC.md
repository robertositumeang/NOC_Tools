# Spesifikasi Logika & SOP: Analisis Massive Site Down VSAT Multi-Vendor

Dokumen ini memuat standar operasional, arsitektur data, dan spesifikasi matematis algoritma korelasi alarm cross-vendor (**ZTE** & **Fiberhome**) pada jaringan akses seluler yang menggunakan transmisi bersama (**Shared VSAT Backhaul**).

---

## 1. Latar Belakang & Latar Masalah Operasional

### 1.1 Karakteristik Lapangan NOC
Dalam infrastruktur jaringan USO / 3T / Remote Area:
1. **Shared Transponder / Hub VSAT**: Beberapa puluhan Base Transceiver Station (BTS / eNodeB) di suatu kluster kepulauan/area terpencil terhubung ke satu hub teleport atau transponder satelit yang sama (dikelola oleh provider seperti Telkomsat, PSN, Lintasarta, Tangara, dll.).
2. **Heterogeneous RAN (Multi-Vendor)**: Di area geografis yang sama, perangkat eNodeB berasal dari vendor berbeda (sebagian **ZTE**, sebagian **Fiberhome**).
3. **Tantangan Blind Spot OSS**:
   - Engineer yang memonitor OSS ZTE hanya melihat sebagian site yang down.
   - Engineer yang memonitor OSS Fiberhome hanya melihat sebagian lainnya.
   - Jika terjadi *carrier drop*, *rain fade* di teleport/hub, atau *transponder glitch*, masing-masing OSS melaporkan jumlah alarm di bawah ambang batas eskalasi darurat, padahal secara agregat transmisi satelit telah terjadi **Massive Outage**.

### 1.2 Alur Trigger Insiden (Incident Workflow)
```
[Tim Hub / Provider VSAT]
          │
          ▼ Mengirim notifikasi: "Traffic drop pada Provider X (Rentang: 14:00 - 15:30)"
[Tim NOC Pusat]
          │
          ├─► Tarik Dump Alarm OSS ZTE
          ├─► Tarik Dump Alarm OSS Fiberhome
          │
          ▼ Ingest ke NOC Massive Checker
[Multi-Vendor Cross-Correlation Engine]
          │
          ▼ Output Laporan Terpadu (Sites at Peak)
[Balasan Eskalasi / RFO ke Tim Provider VSAT]
```

---

## 2. Standard Operating Procedure (SOP) Pengecekan NOC

Berikut langkah-langkah kerja teknisi/engineer NOC saat menerima peringatan penurunan traffic dari tim Hub/VSAT:

### Langkah 1: Pengumpulan Parameter Insiden
Catat informasi awal dari tim Hub/VSAT:
- **Nama Provider VSAT**: (contoh: `TELKOMSAT`, `PSN`, `LINTASARTA`)
- **Spotbeam / Transponder**: (opsional jika spesifik)
- **Rentang Waktu Terindikasi Drop**:
  - `Waktu Mulai (Range Start)`: minimal 15–30 menit sebelum traffic turun tajam.
  - `Waktu Selesai (Range End)`: waktu terkini atau waktu saat traffic dilaporkan pulih.

### Langkah 2: Ekspor Data Log Alarm dari OSS Vendor
- **OSS ZTE (NetNumen / UME)**: Ekspor log alarm aktif & riwayat (*Alarm History*) dalam format `.zip` atau `.xlsx`.
- **OSS Fiberhome (OTNM2000)**: Ekspor log alarm dalam format `.xlsx` atau `.csv`.
- *Catatan*: File dapat langsung ditaruh di folder aplikasi atau dibrowse manual via GUI.

### Langkah 3: Eksekusi Analisis di NOC Massive Checker
1. Buka aplikasi `NOC Dashboard.exe` atau jalankan `python app.py`.
2. Pastikan file master **Site Management** terpilih (default: 1.404 site aktif).
3. Pilih path file ekspor **ZTE** dan **Fiberhome**.
4. Klik **▶ Run Analysis**.
5. Pada panel **Scope & Filters**:
   - Atur **Start Time** dan **End Time** sesuai rentang waktu drop traffic.
   - Filter dropdown **VSAT Providers** ke provider yang dilaporkan.
   - (Opsional) Centang **Breakdown results by Spotbeam** jika ingin melihat sebaran per beam satelit.
   - Klik **⟳ Apply Filter & Scope**.

### Langkah 4: Validasi & Pembacaan Hasil
- Periksa kartu metrik **PEAK CONCURRENT DOWN**: Menampilkan jumlah maksimum site yang padam bersamaan di titik waktu paling kritis.
- Periksa kolom **Massive Down**: Jika $\ge 5$ site (atau ambang batas yang ditentukan), badge akan berwarna merah bertuliskan **YES**.
- Periksa tab **Sites at Peak**: Menampilkan daftar rincian site (ZTE & Fiberhome) yang tumbang bersamaan di jam puncak tersebut.

### Langkah 5: Ekspor Laporan Konfirmasi ke Tim VSAT
- Klik kanan pada baris provider terkait di tabel *VSAT Outage Summary* $\rightarrow$ **Export Selected Rows to Excel...**.
- Sistem otomatis memberi nama file standar:
  `{Jumlah_Site} SITES VSAT DOWN {PAKET} {AREA} UNDER {PROVIDER} {YYYYMMDD}.xlsx`
- Kirimkan file Excel tersebut ke tim Hub/VSAT sebagai bukti validasi korelatif.

---

## 3. Spesifikasi Logika Teknis & Normalisasi Data

### 3.1 Normalisasi Skema Alarm Cross-Vendor
Aplikasi memetakan atribut unik vendor ke dalam skema terpadu (*Unified Schema*):

| Unified Field | Sumber ZTE | Sumber Fiberhome | Sumber Huawei | Keterangan |
| :--- | :--- | :--- | :--- | :--- |
| **Vendor** | `"ZTE"` | `"Fiberhome"` | `"Huawei"` | Dideteksi dari signature header file |
| **Site ID** | Regex / Token dari `ME`, `ME ID` | Regex / Token dari `Fault Source`, `NE ID` | `eNodeB ID`, `Site ID` | Dicocokkan ke Master Database |
| **Alarm Name** | `Alarm Code Name`, `Alarm Name` | `Alarm Name` | `Name`, `Alarm Name` | Nama spesifik alarm |
| **Occurrence Time** | `Occurrence Time` | `Generation Time` | `Occurred On (NT)` | Waktu mulai alarm timbul |
| **Clear Time** | `Clear Time` | `Clear Time` | `Cleared On (NT)` | Waktu alarm normal kembali |
| **Alarm State** | `Active` / `Cleared` | `Active` / `Cleared` | `Active` / `Cleared` | Dihitung dari keberadaan `Clear Time` |

### 3.2 Kamus Alarm Gangguan Transmisi VSAT (*Preferred Down Alarms*)
Untuk mencegah alarm non-transmisi (seperti baterai lemah atau temperatur) dihitung sebagai insiden link satelit, engine memprioritaskan:
- **ZTE**:
  - `The link between the server and the ME is broken`
  - `Communication link failure`
- **Fiberhome**:
  - `NE Disconnected`
  - `Cell out of service`
  - `ENB out of service`
- **Huawei**:
  - `eNodeB Unavailable`
  - `Cell Unavailable`
  - `SCTP Link Congestion`

### 3.3 Pencocokan Master Data (*Site Resolution Hierarchy*)
Untuk menjembatani nama perangkat OSS dengan identitas site resmi:
1. Ekstraksi langsung kode Site ID (contoh: `MLU00001`, `PAP00123`).
2. Pencocokan exact token terhadap himpunan `Site ID` dan `Site ID OPSEL` di database Site Management.
3. Fallback pencocokan `eNodeB ID` / `NE ID` numerik.
4. Pengambilan metadata pelengkap:
   - `VSAT Provider` (dari kolom *Satellite/MW Brand* / *VSAT Provider*)
   - `Spotbeam`
   - `Status BAPL`
   - `Paket Penyedia MSS`
   - `Area / Cluster Provinsi`

---

## 4. Algoritma Perhitungan Waktu Puncak (*Sweep-Line Interval Algorithm*)

Untuk mendeteksi site yang down **pada saat yang bersamaan**, sistem menggunakan algoritma garis sapuan (*sweep-line*) interval berbobot:

```
Timeline: ─────────────────────────────────────────────────────────────► (Waktu)
Site A:       [─────────────────────────────]
Site B:             [─────────────────]
Site C:                   [─────────────────────────]
                    ▲           ▲
                 Count=2     Count=3 (PEAK CONCURRENT)
```

### 4.1 Konstruksi Titik Peristiwa (Event Construction)
Untuk setiap alarm yang lolos filter:
1. Tentukan batas aktif:
   $$t_{\text{start}} = \max(\text{Occurrence Time}, \text{Range Start})$$
   $$t_{\text{end}} = \min(\text{Clear Time} \lor \text{now}, \text{Range End})$$
2. Jika $t_{\text{start}} < t_{\text{end}}$:
   - Tambahkan event mulai: $(t_{\text{start}}, +1, \text{Site ID})$
   - Tambahkan event selesai: $(t_{\text{end}}, -1, \text{Site ID})$

### 4.2 Pelacakan Status Aktif Simultan
Urutkan seluruh event berdasarkan waktu $t$ secara kronologis:
$$\text{active\_counts}(t) = \sum_{t_i \le t} \Delta_i$$
- $\text{Peak Simultaneous Sites} = \max_t (\text{unique sites active pada } t)$
- $\text{Peak Time} = t \text{ saat peak terjadi pertama kali}.$

### 4.3 Kluster Jendela Insiden (Incident Window Filter)
Untuk mengeliminasi site yang mengalami pemadaman permanen/terisolasi sejak hari sebelumnya (misal solar cell rusak):
Sistem menerapkan filter jendela:
$$t_{\text{peak}} - 45\text{ menit} \le \text{Occurrence Time} \le t_{\text{peak}} + 15\text{ menit}$$
Hanya site yang waktu kejadiannya (`Occurrence Time`) berada di dalam jendela $\pm 45$ menit dari waktu puncak yang dikelompokkan ke dalam daftar **Sites at Peak**.

### 4.4 Ambang Batas Insiden Masif (Massive Threshold)
$$\text{Is Massive} = (\text{Peak Simultaneous Sites} \ge \text{Threshold})$$
*Nilai default threshold*: **$\ge 5$ site**. Parameter ini dapat disesuaikan pada kontrol numerik GUI.

---

## 5. Struktur Laporan Luaran Excel

Laporan Excel yang diekspor berisi 3 lembar kerja (*worksheets*):

1. **`Consolidated Alarms`**: Seluruh rekaman alarm gabungan ZTE & Fiberhome yang telah dinormalisasi dalam rentang waktu yang dipilih.
2. **`VSAT Summary`**: Ringkasan per Provider VSAT (atau per Spotbeam) yang memuat:
   - *Current Down Sites*
   - *Peak Simultaneous Sites*
   - *Peak Time*
   - *Status Massive Down (YES/NO)*
3. **`Sites at Peak`**: Rincian seluruh site yang down pada waktu puncak insiden:
   - Nomor, Vendor (ZTE / Fiberhome), Site ID, Site Name, Provider VSAT, Spotbeam, Status BAPL, Paket, Area, Waktu Mulai, Waktu Pulih, Durasi Padam, dan Status Terkini.
