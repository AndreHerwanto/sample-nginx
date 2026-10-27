#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
curl_intermittent_monitor.py
============================
Monitoring berkala berbasis curl untuk memastikan ada/tidaknya masalah
intermittent pada sebuah domain/URL, plus 2 report otomatis:

  1. Health Check Report   -> ringkasan availability, latency, HTTP code, error
  2. Intermittent Report   -> kejadian bermasalah: jam berapa, berapa kali,
                              detail per kejadian (fase lambat/gagal, curl exit code, dll)

Hanya membutuhkan: Python 3.7+ dan curl (tanpa library tambahan).

CONTOH PAKAI
------------
# 1) Monitor GET tiap 30 detik selama 2 jam, report otomatis dibuat di akhir
python3 curl_intermittent_monitor.py monitor https://example.com --interval 30 --duration 120

# 2) Jalan terus sampai Ctrl+C (disarankan dijalankan di tmux/screen/nohup)
nohup python3 curl_intermittent_monitor.py monitor https://example.com -i 30 > monitor.log 2>&1 &

# 3) Tambah test upload (POST multipart) beberapa ukuran, untuk kasus gagal di ukuran tertentu
python3 curl_intermittent_monitor.py monitor https://example.com \
    --upload-kb 50,100,1024 --upload-url https://example.com/endpoint-test-upload

# 4) Generate ulang report kapan saja (boleh saat monitor masih jalan)
python3 curl_intermittent_monitor.py report curl_monitor/samples_*.csv --slow-ms 2000

PERINGATAN: mode --upload-kb mengirim POST nyata. Jangan arahkan ke endpoint
produksi yang menyimpan data (mis. insert artikel). Gunakan endpoint test /
dummy yang aman, atau konfirmasi dulu dengan L2 / pelanggan.
"""

import argparse
import csv
import glob
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse

FIELDS = ["timestamp", "probe", "url", "http_code", "curl_exit", "error",
          "remote_ip", "upload_bytes", "dns_ms", "connect_ms", "tls_ms",
          "ttfb_ms", "total_ms"]
NUM_FIELDS = ["upload_bytes", "dns_ms", "connect_ms", "tls_ms", "ttfb_ms", "total_ms"]

CURL_FMT = ("%{http_code}|%{remote_ip}|%{size_upload}|%{time_namelookup}|"
            "%{time_connect}|%{time_appconnect}|%{time_starttransfer}|%{time_total}")

CURL_ERR = {
    6: "Tidak bisa resolve host (DNS)",
    7: "Gagal connect",
    16: "HTTP/2 framing error",
    18: "Transfer parsial",
    28: "Timeout",
    35: "SSL connect error",
    47: "Terlalu banyak redirect",
    52: "Empty reply dari server",
    55: "Gagal kirim data (send failure)",
    56: "Gagal terima data / connection reset",
    60: "Masalah sertifikat SSL",
    92: "HTTP/2 stream error",
    124: "Subprocess curl timeout",
}


# --------------------------------------------------------------------------- #
# Util
# --------------------------------------------------------------------------- #
def parse_codes(spec):
    ranges = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            ranges.append((int(lo), int(hi)))
        else:
            ranges.append((int(part), int(part)))
    return lambda c: any(lo <= c <= hi for lo, hi in ranges)


def pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def fmt_ms(v):
    return f"{v:,.0f}"


def fmt_dur(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} jam")
    if m:
        parts.append(f"{m} menit")
    if s or not parts:
        parts.append(f"{s} detik")
    return " ".join(parts)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/") for c in r) + " |")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Klasifikasi sample
# --------------------------------------------------------------------------- #
def classify(r, ok_fn, slow_ms):
    if r["curl_exit"] != 0:
        return "FAIL"
    try:
        code = int(r["http_code"])
    except ValueError:
        code = 0
    if not ok_fn(code):
        return "FAIL"
    if slow_ms and r["total_ms"] > slow_ms:
        return "SLOW"
    return "OK"


def reason(r, slow_ms):
    if r["curl_exit"] != 0:
        return f"curl({r['curl_exit']}) {CURL_ERR.get(r['curl_exit'], 'error')}"
    if r["status"] == "FAIL":
        return f"HTTP {r['http_code']}"
    return f"Lambat (> {slow_ms:.0f} ms)"


def phases(r):
    d = r["dns_ms"]
    c = max(r["connect_ms"] - d, 0)
    t = max(r["tls_ms"] - r["connect_ms"], 0) if r["tls_ms"] > 0 else 0
    base = max(r["tls_ms"], r["connect_ms"])
    w = max(r["ttfb_ms"] - base, 0)
    x = max(r["total_ms"] - r["ttfb_ms"], 0)
    return {"DNS": d, "TCP connect": c, "TLS": t, "wait/upload (TTFB)": w, "transfer": x}


def stage(r):
    if r["status"] == "OK":
        return "-"
    if r["status"] == "FAIL":
        if r["curl_exit"] != 0:
            if r["curl_exit"] == 6:
                return "DNS resolve"
            if r["connect_ms"] == 0:
                return "TCP connect"
            if r["https"] and r["tls_ms"] == 0:
                return "TLS handshake"
            if r["ttfb_ms"] == 0:
                if r["upload_bytes"] > 0:
                    return f"Upload terhenti (±{r['upload_bytes'] / 1024:.0f} KB terkirim)"
                return "Menunggu response server"
            return "Transfer response"
        return f"Server membalas HTTP {r['http_code']}"
    ph = phases(r)
    return f"Lambat di {max(ph, key=ph.get)}"


# --------------------------------------------------------------------------- #
# Monitor
# --------------------------------------------------------------------------- #
def build_probes(a):
    probes = []
    if not a.upload_only:
        probes.append({"label": "GET", "method": "GET", "url": a.url, "kb": 0})
    if a.upload_kb:
        for kb in a.upload_kb.split(","):
            kb = int(kb.strip())
            probes.append({"label": f"POST-{kb}KB", "method": "POST",
                           "url": a.upload_url or a.url, "kb": kb})
    if not probes:
        sys.exit("ERROR: --upload-only butuh --upload-kb.")
    return probes


def run_probe(p, a, payloads):
    cmd = ["curl", "-sS", "-o", os.devnull, "-w", CURL_FMT,
           "--max-time", str(a.timeout), "--connect-timeout", str(a.connect_timeout),
           "-A", "L1-curl-monitor/1.0"]
    if a.follow:
        cmd.append("-L")
    if a.insecure:
        cmd.append("-k")
    if a.resolve:
        cmd += ["--resolve", a.resolve]
    for h in (a.header or []):
        cmd += ["-H", h]
    if p["method"] == "POST":
        cmd += ["-F", f"{a.upload_field}=@{payloads[p['kb']]};type=application/octet-stream"]
    cmd.append(p["url"])

    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    row = {"timestamp": ts, "probe": p["label"], "url": p["url"], "http_code": "000",
           "curl_exit": 0, "error": "", "remote_ip": "", "upload_bytes": 0,
           "dns_ms": 0, "connect_ms": 0, "tls_ms": 0, "ttfb_ms": 0, "total_ms": 0}
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout + 10)
        row["curl_exit"] = cp.returncode
        err_lines = (cp.stderr or "").strip().splitlines()
        row["error"] = err_lines[-1][:160] if err_lines else ""
        parts = (cp.stdout or "").strip().split("|")
        if len(parts) == 8:
            row["http_code"] = parts[0]
            row["remote_ip"] = parts[1]
            row["upload_bytes"] = float(parts[2] or 0)
            for key, val in zip(["dns_ms", "connect_ms", "tls_ms", "ttfb_ms", "total_ms"], parts[3:]):
                row[key] = round(float(val or 0) * 1000, 1)
    except subprocess.TimeoutExpired:
        row["curl_exit"] = 124
        row["error"] = "subprocess timeout"
        row["total_ms"] = (a.timeout + 10) * 1000.0
    except FileNotFoundError:
        sys.exit("ERROR: curl tidak ditemukan di PATH.")
    return row


def cmd_monitor(a):
    if shutil.which("curl") is None:
        sys.exit("ERROR: curl tidak ditemukan di PATH.")
    probes = build_probes(a)
    os.makedirs(a.output_dir, exist_ok=True)
    host = urlparse(a.url).hostname or "target"
    start = datetime.now().astimezone()
    csv_path = os.path.join(a.output_dir, f"samples_{host}_{start:%Y%m%d_%H%M%S}.csv")
    ok_fn = parse_codes(a.ok_codes)

    tmpdir = tempfile.mkdtemp(prefix="curlmon_")
    payloads = {}
    for p in probes:
        if p["method"] == "POST" and p["kb"] not in payloads:
            path = os.path.join(tmpdir, f"payload_{p['kb']}kb.bin")
            with open(path, "wb") as fh:
                fh.write(os.urandom(p["kb"] * 1024))
            payloads[p["kb"]] = path

    print(f"Target     : {a.url}")
    print(f"Probe      : {', '.join(p['label'] for p in probes)}")
    print(f"Interval   : {a.interval}s | Timeout: {a.timeout}s | Slow > {a.slow_ms:.0f} ms")
    print(f"Durasi     : {'sampai Ctrl+C' if not a.duration else f'{a.duration} menit'}")
    print(f"Raw data   : {csv_path}")
    if payloads:
        print("PERINGATAN : mode upload mengirim POST nyata; pastikan endpoint aman untuk di-test.")
    print("-" * 78)

    end_at = time.time() + a.duration * 60 if a.duration else None
    try:
        with open(csv_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, FIELDS)
            w.writeheader()
            next_t = time.time()
            while True:
                if end_at and time.time() >= end_at:
                    break
                for p in probes:
                    row = run_probe(p, a, payloads)
                    w.writerow(row)
                    fh.flush()
                    st = classify(row, ok_fn, a.slow_ms)
                    extra = row["error"] if st == "FAIL" else ""
                    print(f"[{row['timestamp'][11:19]}] {p['label']:<12} {st:<5} "
                          f"HTTP {row['http_code']} {row['total_ms']:>8.0f}ms "
                          f"{row['remote_ip']:<16} {extra}", flush=True)
                next_t += a.interval
                delay = next_t - time.time()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_t = time.time()
    except KeyboardInterrupt:
        print("\nDihentikan oleh user (Ctrl+C).")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not a.no_report:
        print("-" * 78)
        build_reports([csv_path], a)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def load_rows(paths):
    rows = []
    for path in paths:
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    r["ts"] = datetime.fromisoformat(r["timestamp"])
                    for k in NUM_FIELDS:
                        r[k] = float(r[k] or 0)
                    r["curl_exit"] = int(r["curl_exit"])
                    rows.append(r)
                except (ValueError, KeyError):
                    continue
    rows.sort(key=lambda r: r["ts"])
    return rows


def analyze(rows, a):
    ok_fn = parse_codes(a.ok_codes)
    for r in rows:
        r["https"] = r["url"].lower().startswith("https")
        r["status"] = classify(r, ok_fn, a.slow_ms)
        r["reason"] = reason(r, a.slow_ms)
        r["stage"] = stage(r)


def verdict(total, fail, slow):
    if total == 0:
        return "NO DATA"
    if fail == total:
        return "DOWN (semua sample gagal)"
    if fail > 0:
        return "INTERMITTENT (ada sample gagal)"
    if slow > 0:
        return "DEGRADED (tidak ada gagal, tapi ada sample lambat)"
    return "HEALTHY"


def counts(rows):
    c = Counter(r["status"] for r in rows)
    return len(rows), c["OK"], c["SLOW"], c["FAIL"]


def median_interval(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["probe"]].append(r["ts"])
    gaps = []
    for lst in by.values():
        gaps += [(b - a).total_seconds() for a, b in zip(lst, lst[1:])]
    return statistics.median(gaps) if gaps else 0


def build_health(rows, a, host, intermittent_file):
    total, ok, slow, fail = counts(rows)
    first, last = rows[0]["ts"], rows[-1]["ts"]
    L = []
    L.append(f"# Health Check Report - {host}\n")
    L.append(f"- **Dibuat**: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %z}")
    L.append(f"- **Periode**: {first:%Y-%m-%d %H:%M:%S} s/d {last:%Y-%m-%d %H:%M:%S} "
             f"({fmt_dur((last - first).total_seconds())}, zona waktu {first:%z})")
    L.append(f"- **Target**: {', '.join(sorted(set(r['url'] for r in rows)))}")
    L.append(f"- **Interval sample (median)**: ±{median_interval(rows):.0f} detik")
    L.append(f"- **Kriteria**: HTTP OK = `{a.ok_codes}`, SLOW = total time > {a.slow_ms:.0f} ms, "
             f"FAIL = curl error atau HTTP code di luar kriteria")
    L.append(f"\n## Status Keseluruhan: **{verdict(total, fail, slow)}**\n")

    # ringkasan per probe
    by = defaultdict(list)
    for r in rows:
        by[r["probe"]].append(r)
    hdr = ["Probe", "Total", "OK", "SLOW", "FAIL", "Availability %", "Success (tanpa lambat) %"]
    tr = []
    for probe, lst in sorted(by.items()):
        t, o, s, f = counts(lst)
        tr.append([probe, t, o, s, f, f"{(o + s) / t * 100:.2f}", f"{o / t * 100:.2f}"])
    tr.append(["**ALL**", total, ok, slow, fail,
               f"{(ok + slow) / total * 100:.2f}", f"{ok / total * 100:.2f}"])
    L.append("## Ringkasan Sample\n")
    L.append(md_table(hdr, tr))
    L.append("\n> Availability = (OK + SLOW) / Total. Success = OK / Total.\n")

    # latency
    L.append("## Latency Total (ms) per Probe\n")
    lr = []
    for probe, lst in sorted(by.items()):
        v = [r["total_ms"] for r in lst if r["status"] != "FAIL"]
        if v:
            lr.append([probe, len(v), fmt_ms(min(v)), fmt_ms(statistics.mean(v)),
                       fmt_ms(pct(v, 50)), fmt_ms(pct(v, 95)), fmt_ms(pct(v, 99)), fmt_ms(max(v))])
        else:
            lr.append([probe, 0, "-", "-", "-", "-", "-", "-"])
    L.append(md_table(["Probe", "n (non-FAIL)", "Min", "Avg", "P50", "P95", "P99", "Max"], lr))
    L.append("\n> Latency dihitung dari sample yang tidak FAIL.\n")

    # rata-rata fase
    L.append("## Rata-rata Waktu per Fase (ms, sample non-FAIL)\n")
    pr = []
    for probe, lst in sorted(by.items()):
        good = [r for r in lst if r["status"] != "FAIL"]
        if not good:
            continue
        agg = defaultdict(list)
        for r in good:
            for k, v in phases(r).items():
                agg[k].append(v)
        pr.append([probe] + [fmt_ms(statistics.mean(agg[k])) for k in
                             ["DNS", "TCP connect", "TLS", "wait/upload (TTFB)", "transfer"]])
    if pr:
        L.append(md_table(["Probe", "DNS", "TCP connect", "TLS", "wait/upload (TTFB)", "transfer"], pr))
    L.append("")

    # distribusi
    L.append("## Distribusi HTTP Code\n")
    hc = Counter(r["http_code"] for r in rows)
    L.append(md_table(["HTTP Code", "Jumlah", "%"],
                      [[k, v, f"{v / total * 100:.2f}"] for k, v in sorted(hc.items())]))
    L.append("\n## Error curl\n")
    ec = Counter(f"curl({r['curl_exit']}) {CURL_ERR.get(r['curl_exit'], 'error')}"
                 for r in rows if r["curl_exit"] != 0)
    if ec:
        L.append(md_table(["Error", "Jumlah"], [[k, v] for k, v in ec.most_common()]))
    else:
        L.append("Tidak ada error curl.")
    L.append("\n## Remote IP yang Merespons\n")
    ips = Counter(r["remote_ip"] or "(kosong)" for r in rows)
    L.append(md_table(["IP", "Jumlah"], [[k, v] for k, v in ips.most_common()]))

    # kesimpulan
    L.append("\n## Kesimpulan Otomatis\n")
    if fail == 0 and slow == 0:
        L.append("- Seluruh sample sukses dan cepat pada periode ini. **Belum ditemukan indikasi intermittent.**")
        L.append("- Jika pelanggan masih melaporkan keluhan, perpanjang periode monitor "
                 "atau ujikan dari jaringan/provider yang berbeda.")
    else:
        L.append(f"- Ditemukan **{fail} sample FAIL** dan **{slow} sample SLOW** dari {total} sample.")
        L.append(f"- Lihat detail waktu & pola pada `{os.path.basename(intermittent_file)}`.")
        if fail == total:
            L.append("- Semua sample gagal -> kondisi ini **bukan intermittent**, melainkan down total.")
    return "\n".join(L) + "\n"


def find_incidents(rows, slow_ms):
    by = defaultdict(list)
    for r in rows:
        by[r["probe"]].append(r)
    res = []
    for probe, lst in by.items():
        cur = None
        for r in lst:
            if r["status"] != "OK":
                if cur is None:
                    cur = {"probe": probe, "start": r["ts"], "end": r["ts"], "n": 0,
                           "FAIL": 0, "SLOW": 0, "max": 0, "reasons": Counter()}
                cur["end"] = r["ts"]
                cur["n"] += 1
                cur[r["status"]] += 1
                cur["max"] = max(cur["max"], r["total_ms"])
                cur["reasons"][r["reason"]] += 1
            elif cur:
                res.append(cur)
                cur = None
        if cur:
            res.append(cur)
    res.sort(key=lambda x: x["start"])
    return res


def build_intermittent(rows, a, host):
    total, ok, slow, fail = counts(rows)
    bad = [r for r in rows if r["status"] != "OK"]
    first, last = rows[0]["ts"], rows[-1]["ts"]
    L = []
    L.append(f"# Intermittent Report - {host}\n")
    L.append(f"- **Dibuat**: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %z}")
    L.append(f"- **Periode**: {first:%Y-%m-%d %H:%M:%S} s/d {last:%Y-%m-%d %H:%M:%S} "
             f"(zona waktu {first:%z})")
    L.append(f"- **Kriteria bermasalah**: FAIL (curl error / HTTP di luar `{a.ok_codes}`) "
             f"atau SLOW (> {a.slow_ms:.0f} ms)")
    L.append(f"\n## Status: **{verdict(total, fail, slow)}**\n")
    L.append(f"- Total sample: **{total}** | OK: {ok} | SLOW: {slow} | FAIL: {fail}")
    L.append(f"- Persentase bermasalah: **{len(bad) / total * 100:.2f}%**")

    if not bad:
        L.append("\nTidak ditemukan sample bermasalah pada periode ini. "
                 "Belum ada bukti intermittent dari sisi monitor.\n")
        return "\n".join(L) + "\n"

    # per jam
    hours = defaultdict(list)
    for r in rows:
        hours[r["ts"].strftime("%Y-%m-%d %H:00")].append(r)
    hrows = []
    for h in sorted(hours):
        lst = hours[h]
        t, o, s, f = counts(lst)
        v = [x["total_ms"] for x in lst if x["status"] != "FAIL"]
        flag = "⚠" if (s + f) else ""
        hrows.append([h, t, o, s, f, f"{(s + f) / t * 100:.1f}",
                      fmt_ms(statistics.mean(v)) if v else "-",
                      fmt_ms(max(v)) if v else "-", flag])
    shown = hrows if len(hrows) <= 48 else [r for r in hrows if r[-1]]
    L.append("\n## Distribusi per Jam (jam berapa terjadi)\n")
    if len(hrows) > 48:
        L.append("_Periode panjang: hanya jam yang bermasalah yang ditampilkan._\n")
    L.append(md_table(["Jam (mulai)", "Total", "OK", "SLOW", "FAIL", "% Bermasalah",
                       "Avg ms", "Max ms", ""], shown))
    worst = sorted(hrows, key=lambda r: (r[3] + r[4]), reverse=True)[:3]
    L.append("\n**Jam paling bermasalah**: " +
             ", ".join(f"{r[0]} ({r[3] + r[4]} kejadian)" for r in worst if r[3] + r[4] > 0))

    # per probe
    by = defaultdict(list)
    for r in rows:
        by[r["probe"]].append(r)
    L.append("\n## Per Probe\n")
    pr = []
    for probe, lst in sorted(by.items()):
        t, o, s, f = counts(lst)
        fl = [x["upload_bytes"] for x in lst if x["status"] == "FAIL" and x["upload_bytes"] > 0]
        stall = f"±{statistics.median(fl) / 1024:.0f} KB" if fl else "-"
        pr.append([probe, t, s, f, f"{(s + f) / t * 100:.1f}", stall])
    L.append(md_table(["Probe", "Total", "SLOW", "FAIL", "% Bermasalah",
                       "Median KB terkirim saat gagal"], pr))

    post = [(int(p.split("-")[1][:-2]), counts(l)) for p, l in by.items() if p.startswith("POST-")]
    if post:
        post.sort()
        failed_sizes = [kb for kb, c in post if c[3] > 0]
        clean_sizes = [kb for kb, c in post if c[3] == 0]
        L.append("\n**Pola ukuran upload**: " +
                 (f"ukuran terkecil yang pernah gagal = {min(failed_sizes)} KB"
                  if failed_sizes else "tidak ada ukuran upload yang gagal") +
                 (f"; ukuran yang selalu sukses = {', '.join(str(k) for k in clean_sizes)} KB"
                  if clean_sizes else "") + ".")

    # error ringkas
    L.append("\n## Jenis Masalah\n")
    rc = Counter(r["reason"] for r in bad)
    sc = Counter(r["stage"] for r in bad)
    L.append(md_table(["Alasan", "Jumlah"], [[k, v] for k, v in rc.most_common()]))
    L.append("")
    L.append(md_table(["Tahap terjadinya", "Jumlah"], [[k, v] for k, v in sc.most_common()]))

    # incident windows
    inc = find_incidents(rows, a.slow_ms)
    L.append(f"\n## Incident Window ({len(inc)} window)\n")
    L.append("_Window = rangkaian sample bermasalah berurutan pada probe yang sama, "
             "sampai ada sample OK._\n")
    irows = []
    for i, x in enumerate(inc, 1):
        dur = (x["end"] - x["start"]).total_seconds()
        irows.append([i, x["probe"], f"{x['start']:%Y-%m-%d %H:%M:%S}", f"{x['end']:%H:%M:%S}",
                      fmt_dur(dur) if x["n"] > 1 else "1 sample", x["n"], x["FAIL"], x["SLOW"],
                      fmt_ms(x["max"]), "; ".join(f"{k} x{v}" for k, v in x["reasons"].most_common(2))])
    L.append(md_table(["#", "Probe", "Mulai", "Selesai", "Durasi", "Sample", "FAIL",
                       "SLOW", "Max ms", "Alasan utama"], irows))

    # detail
    n = min(len(bad), a.max_events)
    L.append(f"\n## Detail Kejadian ({n} dari {len(bad)})\n")
    drows = []
    for r in bad[:n]:
        drows.append([f"{r['ts']:%Y-%m-%d %H:%M:%S}", r["probe"], r["status"], r["http_code"],
                      r["reason"], r["stage"], f"{r['upload_bytes'] / 1024:.0f}" if r["upload_bytes"] else "-",
                      fmt_ms(r["dns_ms"]), fmt_ms(r["connect_ms"]), fmt_ms(r["tls_ms"]),
                      fmt_ms(r["ttfb_ms"]), fmt_ms(r["total_ms"]), r["remote_ip"] or "-"])
    L.append(md_table(["Waktu", "Probe", "Status", "HTTP", "Alasan", "Tahap", "KB terkirim",
                       "DNS", "Connect", "TLS", "TTFB", "Total", "Remote IP"], drows))
    if len(bad) > n:
        L.append(f"\n_{len(bad) - n} kejadian lainnya ada di file CSV raw (naikkan `--max-events`)._")

    L.append("\n## Data untuk Eskalasi ke L2\n")
    L.append("- Tabel *Detail Kejadian* di atas (timestamp, probe, curl exit, remote IP)")
    L.append("- File CSV raw hasil monitor (lampirkan ke tiket)")
    L.append("- Jika gagal hanya dari provider/lokasi tertentu: catat provider, lokasi, dan IP asal pengetesan")
    L.append("- Bila perlu, `tcpdump`/`traceroute`/`mtr` pada jam kejadian yang tercatat di atas")
    L.append("\n> Report ini bersifat internal. Jangan dikirim mentah ke pelanggan "
             "(berisi IP & detail teknis); ringkas dulu sesuai panduan komunikasi pelanggan.")
    return "\n".join(L) + "\n"


def build_reports(paths, a):
    rows = load_rows(paths)
    if not rows:
        sys.exit("ERROR: tidak ada data valid pada file CSV.")
    analyze(rows, a)
    host = urlparse(rows[0]["url"]).hostname or "target"
    os.makedirs(a.output_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    f_health = os.path.join(a.output_dir, f"report_health_{host}_{stamp}.md")
    f_inter = os.path.join(a.output_dir, f"report_intermittent_{host}_{stamp}.md")
    with open(f_inter, "w", encoding="utf-8") as fh:
        fh.write(build_intermittent(rows, a, host))
    with open(f_health, "w", encoding="utf-8") as fh:
        fh.write(build_health(rows, a, host, f_inter))
    total, ok, slow, fail = counts(rows)
    print(f"Sample: {total} (OK {ok} / SLOW {slow} / FAIL {fail}) -> {verdict(total, fail, slow)}")
    print(f"Report 1 (Health Check) : {f_health}")
    print(f"Report 2 (Intermittent) : {f_inter}")


def cmd_report(a):
    paths = []
    for pattern in a.files:
        paths += sorted(glob.glob(pattern)) or [pattern]
    paths = [p for p in paths if os.path.isfile(p)]
    if not paths:
        sys.exit("ERROR: file CSV tidak ditemukan.")
    build_reports(paths, a)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--slow-ms", type=float, default=3000,
                        help="Ambang sample dianggap lambat (ms). Default 3000")
    common.add_argument("--ok-codes", default="200-399",
                        help="HTTP code dianggap sukses, mis. '200-399' atau '200,301,302'. Default 200-399")
    common.add_argument("--output-dir", default="curl_monitor", help="Folder output. Default ./curl_monitor")
    common.add_argument("--max-events", type=int, default=300,
                        help="Maks baris detail kejadian di report. Default 300")

    ap = argparse.ArgumentParser(description="Monitor curl intermittent + report otomatis")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("monitor", parents=[common], help="Jalankan monitoring")
    m.add_argument("url", help="URL target, mis. https://example.com/")
    m.add_argument("-i", "--interval", type=float, default=30, help="Jeda antar siklus (detik). Default 30")
    m.add_argument("-d", "--duration", type=float, default=0,
                   help="Durasi monitor (menit). 0 = sampai Ctrl+C")
    m.add_argument("-t", "--timeout", type=int, default=30, help="curl --max-time (detik). Default 30")
    m.add_argument("--connect-timeout", type=int, default=10, help="curl --connect-timeout. Default 10")
    m.add_argument("-L", "--follow", action="store_true", help="Ikuti redirect")
    m.add_argument("-k", "--insecure", action="store_true", help="Abaikan validasi sertifikat SSL")
    m.add_argument("-H", "--header", action="append", help="Header tambahan (boleh berulang)")
    m.add_argument("--resolve", help="curl --resolve host:port:ip (tes ke IP tertentu)")
    m.add_argument("--upload-kb", help="Daftar ukuran upload POST (KB), mis. 50,100,1024")
    m.add_argument("--upload-url", help="URL endpoint untuk POST upload (default sama dengan url)")
    m.add_argument("--upload-field", default="file", help="Nama field multipart. Default 'file'")
    m.add_argument("--upload-only", action="store_true", help="Hanya probe upload (tanpa GET)")
    m.add_argument("--no-report", action="store_true", help="Jangan buat report otomatis di akhir")
    m.set_defaults(func=cmd_monitor)

    r = sub.add_parser("report", parents=[common], help="Buat report dari file CSV raw")
    r.add_argument("files", nargs="+", help="File CSV (boleh wildcard)")
    r.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
