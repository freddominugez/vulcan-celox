#!/bin/bash
# Runs the test suite in a Linux container (Python 3.9, the minimum version). Needs podman or docker.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="$(command -v podman || command -v docker || true)"
[ -n "$ENGINE" ] || { echo "instale podman ou docker para rodar os testes em Linux"; exit 2; }
IMAGE="${VULCAN_LINUX_IMAGE:-docker.io/library/python:3.9-slim}"
"$ENGINE" run --rm -v "$ROOT":/src:ro "$IMAGE" sh -c '
  set -e
  # copy without the Mac __pycache__, deleting nothing. Without preserving owner and mode: in a container without real
  # root (GitHub CI) tar cannot adjust them
  mkdir /tmp/app && tar -C /src --exclude=__pycache__ -cf - . | tar -C /tmp/app --no-same-owner --no-same-permissions -xf -
  cd /tmp/app
  PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -t .
'
echo "LINUX OK"
