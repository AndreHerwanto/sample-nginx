#!/usr/bin/env bash
# Kirim beberapa request dan hitung pod mana yang menjawab.
# Pemakaian: bash test-lb.sh <IP_FLOATING_LB> [HOST] [JUMLAH]
# Contoh   : bash test-lb.sh 203.0.113.10 hello.testing.local 10
IP="${1:?Pemakaian: bash test-lb.sh <IP_FLOATING_LB> [HOST] [JUMLAH]}"
HOST="${2:-hello.testing.local}"
N="${3:-8}"

for i in $(seq 1 "$N"); do
  out=$(curl -s -m 5 -H "Host: ${HOST}" "http://${IP}" || true)
  pod=$(echo "$out" | grep -o 'id="pod">[^<]*' | sed 's/id="pod">//')
  echo "${pod:-GAGAL}"
done | sort | uniq -c
