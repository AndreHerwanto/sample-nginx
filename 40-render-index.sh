#!/bin/sh
# Dijalankan otomatis oleh entrypoint nginx saat container start.
# Mengisi nama pod, IP, dan node ke halaman web.
POD="${POD_NAME:-$(hostname)}"
NODE="${NODE_NAME:--}"
IP="$(hostname -i 2>/dev/null | awk '{print $1}')"
START="$(date '+%Y-%m-%d %H:%M:%S %Z')"
sed -e "s|__POD__|$POD|g" -e "s|__NODE__|$NODE|g" -e "s|__IP__|$IP|g" -e "s|__START__|$START|g" \
  /usr/share/nginx/template/index.html.tpl > /usr/share/nginx/html/index.html
