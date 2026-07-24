#!/usr/bin/env bash
# 資料HTML → A4 PDF 変換。ページ分割/背景色は各テンプレートの @media print で制御。
# Chromium のパスは環境変数 CHROME で上書き可（既定は Playwright 同梱）。
set -euo pipefail
cd "$(dirname "$0")"
python3 build_cr.py
python3 build_brief.py
CHROME="${CHROME:-/opt/pw-browsers/chromium-1194/chrome-linux/chrome}"
mkdir -p samples/pdf
"$CHROME" --headless=new --no-sandbox --no-pdf-header-footer \
  --print-to-pdf=samples/pdf/cr_directions.pdf "file://$PWD/cr_directions.html"
"$CHROME" --headless=new --no-sandbox --no-pdf-header-footer \
  --print-to-pdf=samples/pdf/design_brief.pdf "file://$PWD/design_brief.html"
echo "wrote samples/pdf/cr_directions.pdf, samples/pdf/design_brief.pdf"
