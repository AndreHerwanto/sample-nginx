#!/usr/bin/env bash
# ==============================================================================
#  install-nginx.sh  |  openSUSE
# ------------------------------------------------------------------------------
#  Memasang nginx versi terbaru + halaman web contoh yang menampilkan hostname.
#
#  Target   : openSUSE Leap 15.x / 16.x dan Tumbleweed
#  Sumber   : nginx.org (Leap) / repo openSUSE (Tumbleweed)
#  Pemakaian: sudo bash install-nginx.sh
#
#  Yang dilakukan script ini (dan HANYA ini):
#    1. Menambahkan repository nginx (+ signing key) dan memasang paket nginx
#    2. Membuat/menimpa index.html di document root nginx (isi: hostname)
#    3. Mengaktifkan & menjalankan service nginx
#
#  Yang TIDAK dilakukan: upgrade paket lain, ubah firewall/SELinux/kernel/SSH,
#  ubah hostname, atau menghapus apa pun.
# ==============================================================================

set -Eeuo pipefail

# ----------------------------------------------------------------------------
#  Konfigurasi (bisa di-override lewat environment variable)
# ----------------------------------------------------------------------------
NGINX_BRANCH="${NGINX_BRANCH:-mainline}"   # mainline = rilis terbaru | stable
PAGE_MARKER="generated-by: install-nginx.sh"

# ----------------------------------------------------------------------------
#  Helper output
# ----------------------------------------------------------------------------
if [[ -t 1 ]]; then
  C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_OFF=$'\033[0m'
else
  C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_OFF=''
fi
info() { printf '%s[INFO]%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s[ OK ]%s %s\n' "$C_OK"   "$C_OFF" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die()  { printf '%s[FAIL]%s %s\n' "$C_ERR"  "$C_OFF" "$*" >&2; exit 1; }

trap 'die "Terjadi error pada baris ${LINENO}: ${BASH_COMMAND}"' ERR

# ----------------------------------------------------------------------------
#  Pengecekan awal
# ----------------------------------------------------------------------------
require_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || die "Jalankan sebagai root, contoh: sudo bash install-nginx.sh"
}

check_branch() {
  case "$NGINX_BRANCH" in
    mainline|stable) ;;
    *) die "NGINX_BRANCH harus 'mainline' atau 'stable' (nilai saat ini: ${NGINX_BRANCH})." ;;
  esac
}

check_port80() {
  command -v ss >/dev/null 2>&1 || return 0
  local other
  other="$(ss -H -ltnp 'sport = :80' 2>/dev/null | grep -v 'nginx' || true)"
  if [[ -n "$other" ]]; then
    warn "Port 80 sedang dipakai proses lain (bukan nginx). nginx mungkin gagal start:"
    warn "$other"
  fi
}

# ----------------------------------------------------------------------------
#  Halaman web contoh (hanya menampilkan hostname)
# ----------------------------------------------------------------------------
HOST_NAME="$(uname -n | tr -cd 'A-Za-z0-9._-')"
HOST_NAME="${HOST_NAME:-unknown-host}"

render_page() {
  local tpl
  tpl="$(cat <<'HTML'
<!DOCTYPE html>
<!-- generated-by: install-nginx.sh -->
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__HOSTNAME__</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    html,body{height:100%}
    body{
      display:flex;align-items:center;justify-content:center;padding:24px;
      font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
      color:#e2e8f0;
      background:
        radial-gradient(900px 500px at 15% 10%,rgba(99,102,241,.35),transparent 60%),
        radial-gradient(800px 500px at 90% 90%,rgba(34,211,238,.28),transparent 60%),
        #0b1120;
    }
    .card{
      width:100%;max-width:640px;text-align:center;padding:56px 32px;
      background:rgba(255,255,255,.06);
      border:1px solid rgba(255,255,255,.12);
      border-radius:24px;
      box-shadow:0 25px 60px rgba(0,0,0,.45);
      -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
    }
    .label{
      font-size:.8rem;letter-spacing:.35em;text-transform:uppercase;color:#94a3b8;
    }
    h1{
      margin:18px 0 28px;
      font-size:clamp(1.6rem,6vw,3rem);font-weight:800;line-height:1.15;
      word-break:break-all;
      background:linear-gradient(90deg,#22d3ee,#818cf8 60%,#c084fc);
      -webkit-background-clip:text;background-clip:text;
      -webkit-text-fill-color:transparent;color:transparent;
    }
    .status{
      display:inline-flex;align-items:center;gap:10px;
      padding:8px 18px;border-radius:999px;font-size:.9rem;color:#a7f3d0;
      background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.35);
    }
    .dot{
      width:10px;height:10px;border-radius:50%;background:#10b981;
      box-shadow:0 0 0 0 rgba(16,185,129,.7);animation:pulse 1.8s infinite;
    }
    @keyframes pulse{
      70%{box-shadow:0 0 0 12px rgba(16,185,129,0)}
      100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}
    }
    footer{margin-top:36px;font-size:.78rem;color:#64748b}
    @media (prefers-reduced-motion:reduce){.dot{animation:none}}
  </style>
</head>
<body>
  <main class="card">
    <div class="label">Hostname</div>
    <h1>__HOSTNAME__</h1>
    <div class="status"><span class="dot"></span>nginx is running</div>
    <footer>Served by nginx</footer>
  </main>
</body>
</html>
HTML
)"
  printf '%s\n' "${tpl//__HOSTNAME__/$HOST_NAME}"
}

# Tulis index.html secara atomik. File asli (jika ada & bukan buatan script ini)
# disimpan sebagai index.html.orig sekali saja.
deploy_page() {
  local dir="$1" target tmp
  target="${dir}/index.html"
  mkdir -p "$dir"
  if [[ -f "$target" && ! -e "${target}.orig" ]] && ! grep -q "$PAGE_MARKER" "$target"; then
    cp -p "$target" "${target}.orig"
  fi
  tmp="$(mktemp "${dir}/.index.XXXXXX")"
  render_page > "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$target"
  # Pastikan label SELinux (jika aktif) mengikuti direktori web
  if command -v restorecon >/dev/null 2>&1; then restorecon -q "$target" || true; fi
  ok "Halaman web dibuat: ${target}"
}

# ----------------------------------------------------------------------------
#  Service & verifikasi
# ----------------------------------------------------------------------------
start_nginx() {
  if ! nginx -t >/dev/null 2>&1; then
    nginx -t || true
    die "Konfigurasi nginx tidak valid."
  fi
  if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now nginx
  else
    warn "systemd tidak terdeteksi; menjalankan nginx secara langsung."
    pgrep -x nginx >/dev/null 2>&1 || nginx
  fi
  ok "Service nginx aktif."
}

verify_http() {
  if ! command -v curl >/dev/null 2>&1; then
    warn "curl tidak tersedia, uji HTTP dilewati."
    return 0
  fi
  local _try
  for _try in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS -m 3 http://127.0.0.1/ 2>/dev/null | grep -qF "$HOST_NAME"; then
      ok "Uji HTTP berhasil: http://127.0.0.1/ menampilkan hostname '${HOST_NAME}'."
      return 0
    fi
    sleep 1
  done
  warn "Halaman belum bisa diakses via http://127.0.0.1/. Cek: systemctl status nginx"
}

summary() {
  printf '\n'
  ok "Selesai."
  printf '    Versi nginx : %s\n' "$(nginx -v 2>&1 | sed 's/^nginx version: //')"
  printf '    Hostname    : %s\n' "$HOST_NAME"
  printf '    Akses       : http://%s/  atau  http://<IP-server>/\n' "$HOST_NAME"
  printf '    Catatan     : firewall TIDAK diubah; buka port 80 sendiri bila diperlukan.\n\n'
}

# ----------------------------------------------------------------------------
#  openSUSE
#    - Leap        : repository resmi nginx.org (paket SLES)
#    - Tumbleweed  : repository resmi openSUSE (rolling, selalu terbaru)
# ----------------------------------------------------------------------------
REPO_ALIAS="nginx-${NGINX_BRANCH}"

detect_os() {
  [[ -r /etc/os-release ]] || die "/etc/os-release tidak ditemukan."
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_PRETTY="${PRETTY_NAME:-openSUSE}"
  case "${ID:-}" in
    opensuse-leap)
      SOURCE="nginx.org"
      MAJOR="${VERSION_ID:-0}"; MAJOR="${MAJOR%%.*}"
      [[ "$MAJOR" == "15" || "$MAJOR" == "16" ]] \
        || die "openSUSE Leap ${VERSION_ID:-?} tidak didukung (butuh Leap 15.x atau 16.x)."
      WEB_ROOT="/usr/share/nginx/html"
      ;;
    opensuse-tumbleweed|opensuse-slowroll)
      SOURCE="distro"
      WEB_ROOT="/srv/www/htdocs"
      ;;
    *) die "Script ini khusus openSUSE (terdeteksi: ${OS_PRETTY})." ;;
  esac
}

install_from_nginx_org() {
  local repo_url
  if [[ "$NGINX_BRANCH" == "stable" ]]; then
    repo_url="https://nginx.org/packages/sles/${MAJOR}"
  else
    repo_url="https://nginx.org/packages/mainline/sles/${MAJOR}"
  fi

  info "Mengimpor signing key nginx.org..."
  rpm --import https://nginx.org/keys/nginx_signing.key

  if ! zypper --non-interactive lr "$REPO_ALIAS" >/dev/null 2>&1; then
    info "Menambahkan repository resmi nginx.org (${NGINX_BRANCH})..."
    zypper --non-interactive addrepo --gpgcheck --type yum --refresh --check \
      "$repo_url" "$REPO_ALIAS" \
      || die "Gagal menambahkan repo ${repo_url} (belum tersedia untuk arsitektur ini, atau tidak ada koneksi)."
  fi
  zypper --non-interactive --gpg-auto-import-keys refresh "$REPO_ALIAS"

  info "Memasang nginx..."
  zypper --non-interactive install nginx
}

install_from_distro() {
  info "Memperbarui metadata repository openSUSE..."
  zypper --non-interactive refresh
  info "Memasang nginx dari repository openSUSE Tumbleweed..."
  zypper --non-interactive install nginx
}

install_nginx() {
  if [[ "$SOURCE" == "nginx.org" ]]; then
    install_from_nginx_org
  else
    install_from_distro
  fi
}

check_latest() {
  if zypper --non-interactive list-updates 2>/dev/null | grep -qE '\|[[:space:]]+nginx[[:space:]]+\|'; then
    warn "Ada pembaruan nginx yang tersedia. Jalankan: zypper update nginx"
  else
    ok "nginx $(rpm -q --qf '%{VERSION}' nginx) sudah versi terbaru dari repository."
  fi
}

# ----------------------------------------------------------------------------
#  Main
# ----------------------------------------------------------------------------
main() {
  require_root
  check_branch
  detect_os
  info "Sistem terdeteksi : ${OS_PRETTY}"
  check_port80
  install_nginx
  check_latest
  deploy_page "$WEB_ROOT"
  start_nginx
  verify_http
  summary
}

# Jalankan main bila dieksekusi langsung / lewat pipe (bukan saat di-source)
if [[ -z "${BASH_SOURCE[0]:-}" || "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
