#!/usr/bin/env bash
# Build dan push image web-test ke private registry.
# Pemakaian: bash build.sh [TAG] [REGISTRY]
# Contoh   : bash build.sh v1 localhost:5000
set -euo pipefail
cd "$(dirname "$0")"

TAG="${1:-v1}"
REGISTRY="${2:-localhost:5000}"
IMAGE="web-test"

command -v docker >/dev/null || { echo "Docker belum terpasang"; exit 1; }

if ! curl -fsS "http://${REGISTRY}/v2/" >/dev/null; then
  echo "Registry ${REGISTRY} tidak bisa diakses."
  echo "Jalankan: docker run -d -p 5000:5000 --restart=always --name registry registry:2"
  exit 1
fi

docker build -t "${IMAGE}:${TAG}" .
docker tag "${IMAGE}:${TAG}" "${REGISTRY}/${IMAGE}:${TAG}"
docker push "${REGISTRY}/${IMAGE}:${TAG}"

echo "=== Isi registry ==="
curl -fsS "http://${REGISTRY}/v2/_catalog"; echo
curl -fsS "http://${REGISTRY}/v2/${IMAGE}/tags/list"; echo
