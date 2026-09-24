#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
PYTHON = APP_DIR / "venv" / "bin" / "python"

if not PYTHON.exists():
    PYTHON = sys.executable

res = subprocess.run([str(PYTHON), "test_all_services.py"], cwd=APP_DIR)
sys.exit(res.returncode)
