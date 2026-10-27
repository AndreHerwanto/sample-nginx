# curl-intermittent-monitor

Script monitoring berbasis `curl` untuk **memastikan ada atau tidaknya masalah intermittent** pada sebuah domain/URL, lengkap dengan dua report otomatis:

1. **Health Check Report** – ringkasan availability, latency, HTTP code, dan error.
2. **Intermittent Report** – kejadian bermasalah: **jam berapa**, **berapa kali**, dan **detail tiap kejadian**.

Dibuat untuk membantu tim L1 Cloud Engineer saat troubleshooting keluhan seperti *"kadang bisa, kadang tidak"*, *"lambat di jam tertentu"*, atau *"upload gagal dari provider tertentu"*.

---

## Fitur

- Hanya butuh **Python 3.7+** dan **curl** (tanpa `pip install`).
- Mencatat waktu tiap fase: DNS, TCP connect, TLS, TTFB, total.
- Mendeteksi tiga kondisi: `OK`, `SLOW` (lebih lambat dari ambang), dan `FAIL` (curl error atau HTTP code tidak sesuai).
- Mode **upload test** (POST multipart dengan beberapa ukuran file) untuk mencari ambang ukuran yang gagal.
- Data mentah disimpan ke **CSV** setiap sample, sehingga aman kalau script terhenti.
- Report bisa dibuat ulang kapan saja, bahkan saat monitor masih berjalan, dengan ambang yang berbeda.
- Cocok dijalankan di background (`nohup`, `tmux`, `systemd`).

---

## Kebutuhan

| Komponen | Keterangan |
|---|---|
| Python | 3.7 atau lebih baru |
| curl | Harus ada di `PATH` (cek: `curl --version`) |
| OS | Linux / macOS / WSL (Windows native belum diuji) |

---

## Instalasi

```bash
git clone https://github.com/<username>/curl-intermittent-monitor.git
cd curl-intermittent-monitor
chmod +x curl_intermittent_monitor.py   # opsional
python3 curl_intermittent_monitor.py --help
```

---

## Quick Start

### 1. Monitor sederhana (GET)

Cek `https://example.com` tiap 30 detik selama 2 jam. Report dibuat otomatis saat selesai.

```bash
python3 curl_intermittent_monitor.py monitor https://example.com -i 30 -d 120
```

Contoh output live:

```
Target     : https://example.com
Probe      : GET
Interval   : 30.0s | Timeout: 30s | Slow > 3000 ms
Durasi     : 120.0 menit
Raw data   : curl_monitor/samples_example.com_20261027_090000.csv
------------------------------------------------------------------------------
[09:00:01] GET          OK    HTTP 200      312ms 93.184.x.x
[09:00:31] GET          SLOW  HTTP 200     3520ms 93.184.x.x
[09:01:01] GET          FAIL  HTTP 000    30001ms 93.184.x.x   curl: (28) Operation timed out
```

### 2. Jalankan terus sampai dihentikan (Ctrl+C)

Tanpa `-d`, monitor berjalan terus. Saat dihentikan dengan Ctrl+C, report tetap dibuat.

```bash
python3 curl_intermittent_monitor.py monitor https://example.com -i 30
```

### 3. Jalankan di background

Cocok untuk monitoring berjam-jam atau berhari-hari.

```bash
# nohup
nohup python3 curl_intermittent_monitor.py monitor https://example.com -i 30 > monitor.log 2>&1 &
echo $!    # simpan PID untuk menghentikan nanti

# atau tmux
tmux new -s curlmon
python3 curl_intermittent_monitor.py monitor https://example.com -i 30
# detach: Ctrl+B lalu D | kembali: tmux attach -t curlmon
```

Menghentikan monitor dan membuat report:

```bash
kill -INT <PID>    # setara Ctrl+C, report akan dibuat
```

> **Zona waktu:** timestamp memakai zona waktu server. Untuk WIB, jalankan dengan `TZ=Asia/Jakarta python3 ...` supaya jam di report sesuai.

### 4. Buat ulang report dari data mentah

```bash
python3 curl_intermittent_monitor.py report curl_monitor/samples_example.com_*.csv
```

Bisa dijalankan saat monitor masih berjalan di terminal lain. Ambang bisa diubah tanpa mengulang monitoring:

```bash
python3 curl_intermittent_monitor.py report curl_monitor/samples_*.csv --slow-ms 1500 --ok-codes 200,301,302
```

---

## Mode Upload Test (opsional)

Untuk kasus seperti *"upload gagal untuk file di atas ukuran tertentu"*, script bisa mengirim POST multipart dengan beberapa ukuran sekaligus:

```bash
python3 curl_intermittent_monitor.py monitor https://example.com \
    --upload-kb 50,100,1024 \
    --upload-url https://example.com/test-upload-endpoint
```

Tiap siklus akan menjalankan probe `GET`, `POST-50KB`, `POST-100KB`, dan `POST-1024KB`. Report menampilkan persentase gagal per ukuran dan perkiraan jumlah KB yang terkirim saat koneksi terhenti.

> ⚠️ **PERINGATAN**
> Mode ini mengirim **POST sungguhan**. **Jangan** diarahkan ke endpoint produksi yang menyimpan data (misalnya insert artikel, form order, dan sejenisnya) karena akan menimbulkan data sampah. Gunakan endpoint test/dummy yang aman, atau konfirmasikan dulu ke L2/pemilik aplikasi.

---

## Daftar Opsi

### `monitor`

| Opsi | Default | Keterangan |
|---|---|---|
| `url` | – | URL target (wajib) |
| `-i`, `--interval` | `30` | Jeda antar siklus (detik) |
| `-d`, `--duration` | `0` | Durasi monitor dalam **menit**. `0` = sampai Ctrl+C |
| `-t`, `--timeout` | `30` | `curl --max-time` (detik) |
| `--connect-timeout` | `10` | `curl --connect-timeout` (detik) |
| `-L`, `--follow` | off | Ikuti redirect |
| `-k`, `--insecure` | off | Abaikan validasi sertifikat SSL |
| `-H`, `--header` | – | Header tambahan, boleh diulang |
| `--resolve` | – | Format `host:port:ip`, untuk menguji IP tertentu (bypass DNS) |
| `--upload-kb` | – | Daftar ukuran upload POST dalam KB, dipisah koma |
| `--upload-url` | sama dengan `url` | Endpoint untuk POST upload |
| `--upload-field` | `file` | Nama field multipart |
| `--upload-only` | off | Hanya probe upload, tanpa GET |
| `--no-report` | off | Jangan buat report otomatis di akhir |

### Opsi bersama (`monitor` dan `report`)

| Opsi | Default | Keterangan |
|---|---|---|
| `--slow-ms` | `3000` | Sample dianggap `SLOW` jika total waktu lebih besar dari nilai ini (ms) |
| `--ok-codes` | `200-399` | HTTP code yang dianggap sukses, contoh `200-399` atau `200,301,302` |
| `--output-dir` | `curl_monitor` | Folder output |
| `--max-events` | `300` | Maks baris detail kejadian di Intermittent Report |

### `report`

```bash
python3 curl_intermittent_monitor.py report <file.csv> [file2.csv ...] [opsi bersama]
```

Mendukung wildcard dan banyak file sekaligus (data digabung dan diurutkan berdasarkan waktu).

---

## Output

Semua file disimpan di folder `curl_monitor/` (atau sesuai `--output-dir`):

```
curl_monitor/
├── samples_<host>_<tanggal>_<jam>.csv           # data mentah tiap sample
├── report_health_<host>_<tanggal>_<jam>.md      # Report 1: Health Check
└── report_intermittent_<host>_<tanggal>_<jam>.md # Report 2: Intermittent
```

### Report 1 – Health Check

- Status keseluruhan: `HEALTHY`, `DEGRADED`, `INTERMITTENT`, atau `DOWN`
- Ringkasan OK / SLOW / FAIL dan availability per probe
- Latency: min, avg, P50, P95, P99, max
- Rata-rata waktu per fase (DNS, connect, TLS, wait, transfer)
- Distribusi HTTP code, error curl, dan remote IP
- Kesimpulan otomatis

### Report 2 – Intermittent

- **Distribusi per jam**: jam berapa terjadi masalah, berapa kali, dan persentasenya
- **Per probe**: probe/ukuran upload mana yang paling sering gagal
- **Jenis masalah** dan **tahap terjadinya**
- **Incident window**: waktu mulai, selesai, durasi, dan alasan utama
- **Detail kejadian**: waktu, HTTP code, alasan, tahap, timing tiap fase, dan IP
- Daftar data yang perlu dilampirkan saat eskalasi

### Arti status

| Status | Kriteria |
|---|---|
| `OK` | curl berhasil, HTTP code sesuai `--ok-codes`, waktu ≤ `--slow-ms` |
| `SLOW` | Berhasil, tetapi waktu total > `--slow-ms` |
| `FAIL` | curl error (exit code ≠ 0) atau HTTP code di luar `--ok-codes` |

### Arti verdict

| Verdict | Arti |
|---|---|
| `HEALTHY` | Semua sample OK |
| `DEGRADED` | Tidak ada FAIL, tapi ada SLOW |
| `INTERMITTENT` | Sebagian sample FAIL dan sebagian OK |
| `DOWN` | Semua sample FAIL (bukan intermittent, melainkan down total) |

### Kolom "Tahap terjadinya"

| Tahap | Arti singkat |
|---|---|
| `DNS resolve` | Gagal resolve domain |
| `TCP connect` | Gagal membuka koneksi TCP (port tertutup, firewall, dsb) |
| `TLS handshake` | Gagal di negosiasi SSL/TLS |
| `Menunggu response server` | Koneksi terbuka, tetapi server tidak membalas |
| `Upload terhenti (±N KB terkirim)` | Transfer upload berhenti di sekitar N KB |
| `Server membalas HTTP xxx` | Server membalas, tetapi dengan error code |
| `Lambat di <fase>` | Sample SLOW, fase tersebut yang paling dominan |

> **Catatan:** nilai "KB terkirim" diambil dari `size_upload` curl, yaitu byte yang sudah dikirim curl ke socket. Ini perkiraan, bukan jaminan byte tersebut sudah diterima server. Untuk bukti yang kuat, kombinasikan dengan `tcpdump`.

### Kode error curl yang sering muncul

| Exit code | Arti |
|---|---|
| 6 | Tidak bisa resolve host (DNS) |
| 7 | Gagal connect |
| 28 | Timeout |
| 35 | SSL connect error |
| 52 | Empty reply dari server |
| 55 | Gagal kirim data |
| 56 | Gagal terima data / connection reset |
| 60 | Masalah sertifikat SSL |

---

## Tips Penggunaan

- **Interval**: 30 detik cukup untuk kebanyakan kasus. Jangan terlalu agresif (di bawah 5 detik) ke server produksi pelanggan.
- **Durasi**: untuk masalah yang muncul di jam tertentu, jalankan minimal 24 jam supaya pola per jam terlihat.
- **Bandingkan provider/lokasi**: jalankan script yang sama dari beberapa jaringan, lalu bandingkan report-nya. Ini membantu membedakan masalah di sisi server dengan masalah di jalur provider tertentu.
- **Menguji IP tertentu**: gunakan `--resolve example.com:443:<IP>` untuk melewati DNS atau membandingkan beberapa IP.
- **Slow terlalu sering?** Naikkan `--slow-ms` sesuai baseline normal aplikasi, lalu generate ulang report dengan `report --slow-ms ...`.

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `curl tidak ditemukan di PATH` | Install curl: `sudo apt install curl` (Debian/Ubuntu) atau `sudo yum install curl` (RHEL/CentOS) |
| Semua sample `FAIL` dengan `curl(60)` | Sertifikat tidak valid. Periksa sertifikat, atau gunakan `-k` untuk pengetesan sementara |
| Semua sample `HTTP 301/302` dianggap gagal | Sesuaikan `--ok-codes`, atau gunakan `-L` untuk mengikuti redirect |
| Jam di report tidak sesuai WIB | Jalankan dengan `TZ=Asia/Jakarta` |
| Report kosong / `tidak ada data valid` | Pastikan file CSV berisi sample (monitor sudah berjalan minimal satu siklus) |

---

## Keamanan dan Privasi

- Script ini **tidak** menyimpan kredensial. Jika memakai `-H "Authorization: ..."`, token tidak ditulis ke CSV, tetapi tetap tercatat di riwayat shell. Hati-hati.
- File CSV dan report berisi **URL, remote IP, dan detail teknis**. Perlakukan sebagai dokumen internal dan **jangan dipublikasikan** ke repository publik atau dikirim mentah ke pelanggan.
- Gunakan `.gitignore` agar folder `curl_monitor/` tidak ikut ter-commit.
- Gunakan script hanya pada sistem yang Anda kelola atau punya izin untuk diuji.

---

## Kontribusi

Issue dan pull request dipersilakan. Ide pengembangan:

- Notifikasi (Telegram / email) saat FAIL beruntun
- Output report dalam format HTML
- Mode multi-URL dalam satu proses

---

## Lisensi

Tentukan lisensi sesuai kebijakan tim/organisasi Anda (misalnya MIT), lalu tambahkan file `LICENSE`.
