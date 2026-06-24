"""
Phase 2.6 — Dashboard launcher.
Run from project root:
    .\\venv\\Scripts\\python.exe run_dashboard.py
Opens: http://localhost:8501
"""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    streamlit_exe = Path(__file__).parent / "venv" / "Scripts" / "streamlit.exe"
    app_path      = Path(__file__).parent / "dashboard" / "app.py"

    subprocess.run([
        str(streamlit_exe), "run", str(app_path),
        "--server.port", "8501",
        "--server.headless", "false",
    ], check=True)
