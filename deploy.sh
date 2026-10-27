#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo 'Created .env. Fill in API address, key and vision model, then run ./deploy.sh again.'
  exit 1
fi
if [[ "${1:-}" == '--docker' ]]; then
  command -v docker >/dev/null || { echo 'Install Docker with Compose first.'; exit 1; }
  docker compose up --build -d --wait --wait-timeout 120
  echo 'Decomposer is ready: http://127.0.0.1:7860'
  exit 0
fi
python_cmd="${DECOMPOSER_PYTHON:-}"
if [[ -z "$python_cmd" ]]; then
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; assert (3,12)<=sys.version_info[:2]<(3,14)' 2>/dev/null; then
      python_cmd="$candidate"; break
    fi
  done
fi
if [[ -z "$python_cmd" ]]; then
  echo 'Python 3.12–3.13 is required. Install it or use ./deploy.sh --docker.'
  exit 1
fi
missing=()
for cmd in node npm soffice pdftoppm tesseract; do
  command -v "$cmd" >/dev/null || missing+=("$cmd")
done
if (( ${#missing[@]} )); then
  if [[ "$(uname -s)" == 'Darwin' ]] && command -v brew >/dev/null; then
    for cmd in "${missing[@]}"; do
      case "$cmd" in
        node|npm) command -v node >/dev/null && command -v npm >/dev/null || brew install node ;;
        soffice) brew install --cask libreoffice ;;
        pdftoppm) brew install poppler ;;
        tesseract) brew install tesseract ;;
      esac
    done
    export PATH="/Applications/LibreOffice.app/Contents/MacOS:$PATH"
  else
    echo "Missing dependencies: ${missing[*]}"
    echo 'Ubuntu/Debian: install Node.js >=20, npm, libreoffice-impress, poppler-utils, tesseract-ocr, fonts-liberation and fonts-noto-cjk; or use ./deploy.sh --docker.'
    exit 1
  fi
fi
node -e 'if(Number(process.versions.node.split(".")[0])<20)process.exit(1)' || { echo 'Node.js >=20 required'; exit 1; }
[[ -x .venv/bin/python ]] || "$python_cmd" -m venv .venv
stamp="$(.venv/bin/python - <<'PY'
import hashlib,sys
from pathlib import Path
print(hashlib.sha256(Path('requirements.lock').read_bytes()+Path('package-lock.json').read_bytes()+sys.version.encode()).hexdigest())
PY
)"
if [[ ! -f .venv/dependencies.sha256 ]] || [[ "$(cat .venv/dependencies.sha256)" != "$stamp" ]] || [[ ! -d node_modules/pptxgenjs ]]; then
  .venv/bin/python -m pip install -r requirements.lock
  npm ci --omit=dev --no-audit --no-fund
  echo "$stamp" > .venv/dependencies.sha256
fi
exec .venv/bin/python serve.py
