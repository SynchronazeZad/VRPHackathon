#!/usr/bin/env bash
# สำหรับ macOS / Linux
#   ./run.sh            -> เปิดหน้าเว็บ Streamlit
#   ./run.sh benchmark  -> รัน Solver กับทุกไฟล์ .vrp ในโฟลเดอร์ data
set -e
cd "$(dirname "$0")"

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ] || ! "$VENV_PY" -c "import sys" >/dev/null 2>&1; then
  echo "[*] สร้าง .venv ใหม่สำหรับเครื่องนี้..."
  rm -rf .venv
  python3 -m venv .venv
fi
if ! "$VENV_PY" -c "import ortools, matplotlib, streamlit" >/dev/null 2>&1; then
  echo "[*] ติดตั้งไลบรารี..."
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r requirements.txt
fi

if [ "$1" = "benchmark" ]; then
  "$VENV_PY" src/CVRP.py
else
  echo "[*] เปิด http://localhost:8501 ในเบราว์เซอร์"
  "$VENV_PY" -m streamlit run src/app.py
fi
