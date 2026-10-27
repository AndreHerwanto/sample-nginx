# nginx-installer

Script bash **satu-perintah** untuk memasang **nginx versi terbaru** beserta **halaman web contoh yang hanya menampilkan hostname** server. Tersedia untuk 6 distro Linux, masing-masing dalam foldernya sendiri dan **mandiri** (tidak butuh file lain).

![License](https://img.shields.io/badge/license-MIT-blue)
![Shell](https://img.shields.io/badge/shell-bash-4EAA25?logo=gnubash&logoColor=white)
![nginx](https://img.shields.io/badge/nginx-latest-009639?logo=nginx&logoColor=white)

---

## Daftar Isi

- [Fitur](#fitur)
- [Struktur Folder](#struktur-folder)
- [OS yang Didukung](#os-yang-didukung)
- [Cara Pakai](#cara-pakai)
- [Apa yang Dilakukan Script (dan Tidak)](#apa-yang-dilakukan-script-dan-tidak)
- [Bagaimana Versi "Terbaru" Didapat](#bagaimana-versi-terbaru-didapat)
- [Opsi Konfigurasi](#opsi-konfigurasi)
- [Tampilan Halaman Web](#tampilan-halaman-web)
- [Verifikasi](#verifikasi)
- [Uninstall](#uninstall)
- [Troubleshooting](#troubleshooting)
- [Catatan Keamanan](#catatan-keamanan)
- [Lisensi](#lisensi)

---

## Fitur

- **Versi terbaru** dari repository resmi (nginx.org *mainline*, atau repo resmi distro untuk rolling release) dengan verifikasi GPG.
- **Aman untuk VM Anda**: hanya memasang nginx; tidak ada upgrade paket lain, tidak mengubah firewall, SELinux, SSH, atau hostname.
- **Idempotent**: boleh dijalankan berulang kali (otomatis meng-upgrade nginx jika ada rilis baru).
- **Validasi otomatis**: cek OS, cek ketersediaan repo, `nginx -t`, dan uji HTTP ke `127.0.0.1`.
- **Halaman web modern** (HTML+CSS tanpa dependensi eksternal) yang menampilkan hostname.
- Output berwarna, pesan error jelas, berhenti seketika jika ada langkah yang gagal (`set -Eeuo pipefail`).

## Struktur Folder

```text
nginx-installer/
├── README.md
├── LICENSE
├── .gitattributes
├── ubuntu/
│   └── install-nginx.sh
├── debian/
│   └── install-nginx.sh
├── centos/
│   └── install-nginx.sh
├── rhel/
│   └── install-nginx.sh
├── opensuse/
│   └── install-nginx.sh
└── kali/
    └── install-nginx.sh
```

## OS yang Didukung

| Folder     | OS / Versi                                         | Sumber nginx                              | Package manager |
|------------|----------------------------------------------------|-------------------------------------------|-----------------|
| `ubuntu`   | Ubuntu 22.04, 24.04, 25.10, 26.04                  | nginx.org (mainline)                      | apt             |
| `debian`   | Debian 11, 12, 13                                  | nginx.org (mainline)                      | apt             |
| `centos`   | CentOS Stream 9 / 10 (dan CentOS 8)                | nginx.org (mainline)                      | dnf             |
| `rhel`     | RHEL 8 / 9 / 10 (+ Rocky, AlmaLinux, Oracle Linux) | nginx.org (mainline)                      | dnf             |
| `opensuse` | Leap 15.x / 16.x, Tumbleweed                       | nginx.org (Leap) / repo openSUSE (TW)     | zypper          |
| `kali`     | Kali Linux (kali-rolling)                          | Repo resmi Kali                           | apt             |

> Arsitektur: `x86_64` dan `aarch64` selama nginx.org menyediakan paketnya untuk rilis OS tersebut. Jika tidak tersedia, script berhenti dengan pesan yang jelas **sebelum** mengubah sistem.
> CentOS 7 / RHEL 7 sudah EOL dan sengaja tidak didukung.

## Cara Pakai

Semua script harus dijalankan sebagai **root** (atau dengan `sudo`).

### Opsi 1 — Clone repository

```bash
git clone https://github.com/<USERNAME>/nginx-installer.git
cd nginx-installer

# pilih folder sesuai OS Anda, contoh Ubuntu:
sudo bash ubuntu/install-nginx.sh
```

### Opsi 2 — Satu baris (`curl | bash`)

```bash
# Ubuntu
curl -fsSL https://raw.githubusercontent.com/<USERNAME>/nginx-installer/main/ubuntu/install-nginx.sh | sudo bash

# Debian
curl -fsSL https://raw.githubusercontent.com/<USERNAME>/nginx-installer/main/debian/install-nginx.sh | sudo bash

# CentOS
curl -fsSL https://raw.githubusercontent.com/<USERNAME>/nginx-installer/main/centos/install-nginx.sh | sudo bash

# RHEL
curl -fsSL https://raw.githubusercontent.com/<USERNAME>/nginx-installer/main/rhel/install-nginx.sh | sudo bash

# openSUSE
curl -fsSL https://raw.githubusercontent.com/<USERNAME>/nginx-installer/main/opensuse/install-nginx.sh | sudo bash

# Kali Linux
curl -fsSL https://raw.githubusercontent.com/<USERNAME>/nginx-installer/main/kali/install-nginx.sh | sudo bash
```

> Ganti `<USERNAME>` dengan akun GitHub Anda. Sebagai praktik baik, baca isi script terlebih dahulu sebelum menjalankannya via pipe.

Contoh output:

```text
[INFO] Sistem terdeteksi : Ubuntu 24.04.4 LTS
[INFO] Memeriksa repository nginx.org untuk Ubuntu 'noble' (mainline)...
[INFO] Menambahkan repository resmi nginx.org...
[INFO] Memasang nginx...
[ OK ] nginx 1.29.x-1~noble sudah versi terbaru dari repository.
[ OK ] Halaman web dibuat: /usr/share/nginx/html/index.html
[ OK ] Service nginx aktif.
[ OK ] Uji HTTP berhasil: http://127.0.0.1/ menampilkan hostname 'web-01'.
```

## Apa yang Dilakukan Script (dan Tidak)

**Dilakukan** (hanya ini):

1. Memasang prasyarat minimal **hanya jika belum ada** (`curl`, `gnupg`, `ca-certificates` pada keluarga Debian).
2. Menambahkan repository nginx + signing key, lalu memasang/meng-upgrade paket `nginx`.
3. Menulis `index.html` (berisi hostname) di document root nginx. Jika sudah ada `index.html` lain, disimpan dulu sebagai `index.html.orig`.
4. Menjalankan `systemctl enable --now nginx`.

**Tidak dilakukan:**

- `apt upgrade` / `dnf upgrade` / `zypper update` untuk paket lain (hanya `apt-get update` / refresh metadata repo).
- Mengubah firewall (`ufw`, `firewalld`, `iptables`), SELinux/AppArmor, kernel, SSH, user, atau hostname.
- Menghapus paket atau file apa pun.

## Bagaimana Versi "Terbaru" Didapat

Paket nginx bawaan distro (terutama Ubuntu LTS, Debian, RHEL) umumnya **tertinggal jauh**. Karena itu:

| OS | Strategi |
|----|----------|
| Ubuntu, Debian | Repo apt resmi **nginx.org** + *apt pinning* (prioritas 900) agar paket nginx.org selalu menang atas paket distro. |
| CentOS, RHEL | Repo dnf resmi **nginx.org** dengan `gpgcheck=1` dan `module_hotfixes=true` (mengalahkan modul nginx di AppStream). |
| openSUSE Leap | Repo zypper resmi **nginx.org** (paket SLES, GPG aktif). |
| openSUSE Tumbleweed | Repo resmi openSUSE (rolling release, sudah yang terbaru). |
| Kali Linux | Repo resmi Kali. nginx.org tidak menyediakan paket untuk `kali-rolling`, dan mencampur repo distro lain di sistem rolling berisiko merusak dependensi. |

Di akhir proses, script membandingkan versi terpasang dengan kandidat terbaru di repository dan menampilkan hasilnya.

**mainline vs stable:** *mainline* (default) adalah rilis terbaru yang menerima semua fitur, perbaikan bug, dan perbaikan keamanan. *stable* hanya menerima backport perbaikan kritis. Untuk tujuan "selalu terbaru", gunakan *mainline*.

## Opsi Konfigurasi

| Variabel        | Default    | Keterangan                                                          |
|-----------------|------------|---------------------------------------------------------------------|
| `NGINX_BRANCH`  | `mainline` | `mainline` (terbaru) atau `stable`. Tidak berlaku di Kali/Tumbleweed. |

Contoh:

```bash
sudo NGINX_BRANCH=stable bash ubuntu/install-nginx.sh
```

## Tampilan Halaman Web

Halaman berupa kartu *glassmorphism* bertema gelap, responsif, tanpa JavaScript dan tanpa file/font eksternal. Isinya hanya **hostname** server dan indikator "nginx is running".

Hostname diambil saat script dijalankan (`uname -n`) lalu disanitasi (hanya `A-Z a-z 0-9 . _ -`). Jika hostname diubah kemudian, jalankan ulang script untuk memperbarui halaman.

Lokasi file:

| OS                                              | Document root              |
|-------------------------------------------------|----------------------------|
| Ubuntu, Debian, CentOS, RHEL, openSUSE Leap     | `/usr/share/nginx/html/`   |
| Kali Linux                                      | `/var/www/html/`           |
| openSUSE Tumbleweed                             | `/srv/www/htdocs/`         |

## Verifikasi

```bash
nginx -v                                   # versi terpasang
systemctl status nginx --no-pager          # status service
curl -s http://127.0.0.1/ | grep '<h1>'    # harus menampilkan hostname
```

Dari komputer lain: buka `http://<IP-server>/` di browser (pastikan port 80 sudah diizinkan di firewall/security group).

## Uninstall

<details>
<summary><b>Ubuntu / Debian</b></summary>

```bash
sudo systemctl disable --now nginx
sudo apt-get purge -y nginx
sudo rm -f /etc/apt/sources.list.d/nginx.list /etc/apt/preferences.d/99nginx /usr/share/keyrings/nginx-archive-keyring.gpg
sudo apt-get update
```
</details>

<details>
<summary><b>Kali Linux</b></summary>

```bash
sudo systemctl disable --now nginx
sudo apt-get purge -y nginx
sudo rm -f /var/www/html/index.html
```
</details>

<details>
<summary><b>CentOS / RHEL</b></summary>

```bash
sudo systemctl disable --now nginx
sudo dnf remove -y nginx
sudo rm -f /etc/yum.repos.d/nginx.repo
```
</details>

<details>
<summary><b>openSUSE</b></summary>

```bash
sudo systemctl disable --now nginx
sudo zypper --non-interactive remove nginx
sudo zypper --non-interactive removerepo nginx-mainline   # hanya Leap
```
</details>

## Troubleshooting

| Gejala | Penyebab & solusi |
|--------|-------------------|
| `nginx.org belum menyediakan paket untuk ...` | Rilis OS belum didukung nginx.org, arsitektur tidak tersedia, atau server tidak bisa mengakses `nginx.org`. Cek koneksi/proxy: `curl -I https://nginx.org`. |
| `Port 80 sedang dipakai proses lain` | Apache/web server lain memakai port 80. Hentikan dulu, atau ubah port nginx di `/etc/nginx/conf.d/default.conf`. |
| `Konfigurasi nginx tidak valid` | Jalankan `nginx -t` untuk melihat detail. Pada host tanpa IPv6, hapus baris `listen [::]:80;` pada konfigurasi. |
| Halaman tidak bisa dibuka dari luar | Firewall/security group belum membuka port 80. Script ini sengaja **tidak** mengubah firewall. |
| RHEL: gagal mengunduh dependensi | Pastikan sistem terdaftar (subscription) atau repo BaseOS/AppStream dapat diakses; nginx.org hanya menyediakan paket nginx, dependensi (openssl, pcre2, dll.) berasal dari repo OS. |
| `nginx` sudah terpasang dari repo distro | Script akan meng-upgrade ke versi nginx.org. Untuk host produksi dengan konfigurasi khusus, backup `/etc/nginx` terlebih dahulu. |

## Catatan Keamanan

- Menjalankan versi terbaru memperkecil risiko kerentanan yang sudah diketahui, tetapi **bukan jaminan** bebas celah. Jalankan script ini berkala atau aktifkan update otomatis untuk repo nginx.
- Selalu tinjau script sebelum dijalankan dengan hak root, terutama jika memakai `curl | bash`.
- Paket diverifikasi dengan GPG (`gpgcheck=1` / `signed-by=`). Kunci diambil dari `https://nginx.org/keys/nginx_signing.key`.
- Pertimbangkan HTTPS (mis. Let's Encrypt) dan firewall sebelum membuka server ke internet.

## Lisensi

[MIT](LICENSE) — bebas dipakai dan dimodifikasi.
