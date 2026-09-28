<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Web Test - Deka Harbor</title>
<style>
  body{margin:0;font-family:Arial,Helvetica,sans-serif;background:#f3f6fb;color:#1f2937}
  .top{background:#12325b;color:#fff;padding:28px 20px;text-align:center}
  .top h1{margin:0 0 6px;font-size:26px}
  .top p{margin:0;color:#b9cdeb}
  .card{max-width:560px;margin:24px auto;background:#fff;border-radius:10px;padding:8px 22px 18px;
        box-shadow:0 2px 10px rgba(18,50,91,.12)}
  .row{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid #e5eaf2}
  .row:last-of-type{border-bottom:0}
  .k{color:#6b7280}
  .v{font-family:Consolas,Menlo,monospace;font-weight:bold;color:#0070c0;text-align:right;word-break:break-all}
  .ok{display:inline-block;background:#e7f6f3;color:#0f766e;border-radius:20px;padding:4px 12px;font-size:13px;font-weight:bold}
  button{background:#0070c0;color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:14px;cursor:pointer;margin-top:10px}
  .foot{text-align:center;color:#6b7280;font-size:12px;margin-bottom:24px}
</style>
</head>
<body>
  <div class="top">
    <h1>Web Test Berhasil</h1>
    <p>Image ditarik dari private registry 192.168.10.19:5000</p>
  </div>
  <div class="card">
    <div class="row"><span class="k">Status</span><span class="ok">Running</span></div>
    <div class="row"><span class="k">Nama pod</span><span class="v" id="pod">__POD__</span></div>
    <div class="row"><span class="k">IP pod</span><span class="v" id="ip">__IP__</span></div>
    <div class="row"><span class="k">Node</span><span class="v" id="node">__NODE__</span></div>
    <div class="row"><span class="k">Pod mulai</span><span class="v" id="start">__START__</span></div>
    <div class="row"><span class="k">Versi image</span><span class="v">web-test:v1</span></div>
    <div class="row"><span class="k">Waktu browser</span><span class="v" id="now">-</span></div>
    <button onclick="location.reload()">Muat ulang</button>
  </div>
  <div class="foot">Muat ulang beberapa kali: nama pod berubah jika ada lebih dari satu replika.</div>
  <script>document.getElementById('now').textContent=new Date().toLocaleString('id-ID');</script>
</body>
</html>
