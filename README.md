# web-test

Image nginx berisi halaman web siap pakai untuk menguji pull image dari private registry
dan akses lewat load balancer Deka Harbor. Halaman menampilkan **nama pod, IP pod, dan node**
yang melayani request, jadi mudah melihat pod mana yang menjawab.

## Isi repo

| File | Fungsi |
| --- | --- |
| `Dockerfile` | Resep image (nginx:alpine + halaman web) |
| `default.conf` | Konfigurasi nginx, termasuk endpoint `/healthz` |
| `index.html.tpl` | Template halaman web |
| `40-render-index.sh` | Mengisi nama pod, IP, dan node saat container start |
| `build.sh` | Build, tag, dan push image ke registry |
| `test-lb.sh` | Kirim beberapa request dan hitung pod yang menjawab |
| `k8s/deploy.yaml` | Namespace, Deployment (3 replika), Service, dan Ingress |

## 1. Build dan push (di VM registry 192.168.10.19)

```bash
apt install -y git          # jika git belum ada
git clone <URL_REPO> web-test
cd web-test
bash build.sh               # default: tag v1, registry localhost:5000
```

Hasil akhir yang benar:

```
{"repositories":["web-test"]}
{"name":"web-test","tags":["v1"]}
```

Syarat: container `registry` berjalan (`docker ps`) dan VM punya akses internet
atau image `nginx:alpine` sudah ada di VM (`docker images | grep nginx`).

Tes lokal (opsional):

```bash
docker run -d --name web-test -p 8081:80 -e POD_NAME=demo -e NODE_NAME=vm web-test:v1
curl http://localhost:8081/healthz
docker rm -f web-test
```

## 2. Deploy (di jumphost)

```bash
git clone <URL_REPO> web-test
cd web-test
kubectl apply -f k8s/deploy.yaml
kubectl get pods,svc,ingress -n testing-hello-lb -o wide
```

Semua node yang menjalankan pod harus sudah punya `/etc/rancher/k3s/registries.yaml`
yang mengizinkan `192.168.10.19:5000` lewat HTTP, kalau tidak pod akan `ImagePullBackOff`.

Jika cluster tidak punya IngressClass default, hapus tanda `#` pada `ingressClassName`
di `k8s/deploy.yaml` dan isi sesuai hasil `kubectl get ingressclass`.

## 3. Uji

Dari dalam jaringan (ganti IP dengan IP node):

```bash
curl -H "Host: hello.testing.local" http://192.168.208.108
```

Lewat IP floating load balancer (port 80):

```bash
bash test-lb.sh <IP_FLOATING_LB>
```

Contoh hasil: tiga nama pod berbeda dengan jumlah request masing-masing.

## 4. Simulasi registry mati

Di VM registry:

```bash
docker stop registry
```

Di jumphost:

```bash
bash test-lb.sh <IP_FLOATING_LB>                       # tetap menjawab
kubectl delete pod -n testing-hello-lb <nama-satu-pod>
kubectl get pods -n testing-hello-lb -o wide -w        # pod baru harus Running
kubectl describe pod -n testing-hello-lb -l app=hello | grep -E "already present|ErrImagePull"
```

Pod baru yang `Running` dengan pesan `already present on machine` berarti image diambil dari
cache node. `ImagePullBackOff` berarti pod dijadwalkan ke node yang belum punya cache image.

Nyalakan lagi: `docker start registry`.

## 5. Bersihkan

```bash
kubectl delete namespace testing-hello-lb
```

## Catatan

- Jika mengganti tag (misalnya `bash build.sh v2`), ubah juga `image:` di `k8s/deploy.yaml`.
- Untuk registry lain: `bash build.sh v1 <host:port>` lalu sesuaikan `image:` di manifest.
- Repo ini memuat alamat IP internal, sebaiknya dibuat sebagai **private repository**.
- Jika file dibuat di Windows, `.gitattributes` menjaga akhir baris tetap LF. Akhir baris CRLF
  pada `40-render-index.sh` membuat container gagal start.
