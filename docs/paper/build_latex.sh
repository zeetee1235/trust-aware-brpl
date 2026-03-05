#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v latexmk >/dev/null 2>&1; then
  echo "latexmk not found. Install TeX Live latexmk package first."
  exit 1
fi

latexmk -pdf -interaction=nonstopmode -halt-on-error paper_draft.tex

echo "Built: $ROOT_DIR/paper_draft.pdf"
