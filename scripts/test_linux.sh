#!/bin/bash
# Roda a suíte de testes num contêiner Linux (Python 3.9, a versão mínima). Precisa de podman ou docker.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="$(command -v podman || command -v docker || true)"
[ -n "$ENGINE" ] || { echo "instale podman ou docker para rodar os testes em Linux"; exit 2; }
IMAGE="${VULCAN_LINUX_IMAGE:-docker.io/library/python:3.9-slim}"
"$ENGINE" run --rm -v "$ROOT":/src:ro "$IMAGE" sh -c '
  set -e
  # cópia sem os __pycache__ do Mac, sem apagar nada (regra D7). Sem manter dono e modo: em contêiner sem root
  # de verdade (CI do GitHub) o tar não consegue ajustá-los (vt-32 C1)
  mkdir /tmp/app && tar -C /src --exclude=__pycache__ -cf - . | tar -C /tmp/app --no-same-owner --no-same-permissions -xf -
  cd /tmp/app
  PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -t .
'
echo "LINUX OK"
