# Extract CCTV ScreenShot v.1.0.0

Aplikasi desktop Windows untuk memproses screenshot HoloSens dan mengisi
template CCTV Excel. Seluruh pemrosesan berjalan lokal; aplikasi tidak
mengirim data dan tidak membutuhkan koneksi internet setelah dependensi
terpasang.

## Menjalankan dari source

1. Gunakan Python 3.10 atau lebih baru.
2. Instal dependensi:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Jalankan aplikasi:

   ```powershell
   python cctv_report_app.py
   ```

## Alur kerja

Jendela utama dibagi menjadi dua tab: **Import & proses** untuk memilih
template/sumber gambar dan mengatur crop, serta **Periksa & lengkapi data**
untuk meninjau hasil, memeriksa Site ID, dan mengekspor laporan. Pada tab
**Import & proses**, **Sumber data** berada di atas **Kalibrasi crop**.
Instruksi kalibrasi berada di atas tab profil ZTE/FH/Paket 11; tombol reset
crop, proses, proses ulang, dan progress berada di bawah area tab. Aplikasi
terbuka dalam keadaan maximize agar area kerja lebih luas.

Selama ekstraksi gambar, proses crop, atau ekspor ke template Excel, indikator
global di atas kedua tab akan berputar dan menampilkan progress selama proses
berlangsung; setelah berhasil akan muncul animasi centang, dan jika gagal
akan muncul indikator error. Saat ekspor, status tetap terlihat meskipun tab
**Periksa & lengkapi data** sedang terbuka.
Konversi Picture in Cell menampilkan jumlah gambar yang sudah dicoba, jumlah
berhasil/gagal, serta perkiraan sisa waktu setelah 10 gambar pertama. Jika tidak
ada pembaruan selama 1 menit, status memberi tahu bahwa Excel mungkin belum
merespons; ekspor belum otomatis dibatalkan.

1. Pilih workbook template yang berisi kolom `Site ID` dan `Site Name`.
   Gunakan tombol **Reset data** untuk mengosongkan sesi dan memulai laporan
   baru; file sumber dan hasil ekspor tidak ikut dihapus.
2. Untuk melanjutkan laporan dari workbook lain, pilih template terlebih
   dahulu, lalu tekan **Import gambar dari Excel** dan pilih workbook sumber.
   Workbook sumber tidak menggantikan template yang sudah dipilih. Jika
   template belum dipilih, workbook sumber dipakai juga sebagai dasar output.
   Contohnya, `Report CCTV Paket 11_Okt-26.xlsx` dapat dipilih sebagai template
   dan `Report CCTV Paket 11_Okt-26 Malam.xlsx` sebagai sumber; pada workbook
   tersebut aplikasi menemukan 1.971 crop untuk 657 Site ID, dan semua ID itu
   tersedia di template.
   Gambar floating pada sheet `ZTE`, `FH`, dan `Capture` dicocokkan
   dengan Site ID di kolom A. Picture in Cell pada kolom gambar di sheet
   `Site List` juga dibaca sebagai crop yang sudah diproses, sehingga dapat
   langsung diekspor tanpa menjalankan crop ulang. Gambar floating pada kolom
   gambar `Site List` dikenali dengan cara yang sama. Workbook lama yang
   memakai sheet `Capture` tetap didukung: profil Paket 10 ZTE/FH ditentukan
   per Site ID dari konsorsiumnya, sedangkan Paket 11 memakai profil crop
   HoloSens lama. Screenshot Paket 10 yang belum memiliki crop di sheet sumber
   tetap memakai profil ZTE atau FH masing-masing saat diproses.
   Workbook dengan format Site List 9 kolom tetap dipertahankan; kolom
   Kebersihan ditambahkan saat ekspor bila belum ada.
3. Atau pilih satu atau lebih screenshot HoloSens dari file, atau salin
   screenshot ke clipboard lalu tekan **Ctrl+V** / **Paste gambar**. Gambar
   clipboard diproses langsung tanpa perlu disimpan manual. Site ID pada nama
   file, misalnya `PAB0016.png`, akan diisi otomatis; gambar clipboard dan
   file tanpa ID dapat dilengkapi manual pada tabel.
4. Pilih tab **ZTE**, **FH / Fiberhome**, atau **Paket 11 / HoloSens lama**
   untuk meninjau screenshot dan mengatur crop masing-masing tipe. Profil
   Paket 11 mempertahankan posisi crop versi sebelumnya. Sesuaikan kotak crop
   pada screenshot tipe tersebut, lalu pilih ukuran gambar dan tekan
   **Proses screenshot**.
   Preset ukuran crop mengikuti HTML: Kecil panel/kamera 260/360 px,
   Sedang 360/520 px, Besar 480/760 px.
5. Periksa hasil crop, status kamera, kebersihan, NVR, dan keterangan. Status
   kamera ditebak dari tingkat terang/variasi crop; seluruh nilai tetap dapat
   dikoreksi di tabel. Gunakan **Lihat ID duplikat** untuk meninjau screenshot
   dengan Site ID sama dan menghapus satu baris yang dipilih. **Cek Site ID &
   screenshot kosong** merangkum ID duplikat pada template dan sesi, site pada
   template yang belum memiliki screenshot di sesi ini, serta screenshot yang
   belum memiliki Site ID. Klik dua kali sel teks untuk mengeditnya; klik dua
   kali thumbnail untuk melihat screenshot asli. Pilihan Kebersihan mencakup
   `Bersih`, `Kurang Bersih`, `Tidak Bersih`, dan `Not Detected`.
6. Pilih format gambar di samping tombol ekspor, lalu tekan
   **Ekspor ke template Excel**. **Floating** menjadi pilihan default dan
   menyimpan gambar sebagai objek yang dipaskan serta ditambatkan pada sel;
   pilihan ini tidak memerlukan automasi Excel dan lebih kompatibel dengan
   Excel versi lama. **Picture in Cell** tetap tersedia dan memerlukan
   Microsoft 365 Excel dengan fitur **Place in Cell**. Kedua pilihan menyimpan
   hasil ke file baru, bukan menimpa template. Template 13 kolom menerima crop
   gambar pada B-D; workbook sumber 9 kolom tetap mempertahankan format laporan
   dan mengisi status CCTV di sheet `Site List`.
   Untuk mengubah laporan yang sudah tersimpan dengan gambar floating, pilih
   workbook laporan tersebut sebagai template, impor workbook yang sama lewat
   **Import gambar dari Excel**, pilih **Picture in Cell**, lalu ekspor dengan
   nama file baru. Gambar floating pada sel laporan yang diekspor ulang akan
   diganti, bukan ditumpuk.

Site yang tidak terdapat pada template dan screenshot tambahan untuk Site ID
yang sama ditambahkan sebagai baris baru. Kolom konsorsium dan paket untuk
baris tambahan akan mengikuti baris data pertama di template. Baris site lain
yang tidak diproses tetap dipertahankan.

Versi desktop ini tidak memakai OCR. Site ID diambil dari nama file jika
memiliki pola seperti `PAB0016.png`; jika tidak, ID dapat diketik manual
sebelum ekspor.

## Membuat executable Windows

Instal PyInstaller di environment yang sama, kemudian jalankan:

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean CCTVReportBuilder.spec
```

Executable tersedia di `dist\Extract CCTV ScreenShot v.1.0.0.exe`. Simpan template dan
gambar kerja di folder yang dapat dibaca/ditulis oleh akun Windows yang
menjalankan aplikasi. Ikon aplikasi bersumber dari
`assets\cctv-report-icon.svg` dan tersedia sebagai `.ico` untuk executable
Windows.
