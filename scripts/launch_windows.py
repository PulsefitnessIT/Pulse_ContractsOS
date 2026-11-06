"""Windows localhost DEMONSTRATION launcher for Pulse Contracts OS.

Uses bundled Python runtime (PyInstaller) but exposes only 127.0.0.1.
Never intended as a shared staff server or live customer/Sicon installation.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8765


def root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def check_demo_data(folder):
    approved = folder / "approved_master.xlsx"
    if not approved.exists():
        raise RuntimeError(
            "Missing fictional approved_master.xlsx. Re-extract the entire "
            "Windows ZIP into its own folder, including the data directory."
        )
    if (folder / "LIVE_DATA_DO_NOT_RUN.txt").exists():
        raise RuntimeError("Refusing to open a folder marked as live company data.")


def open_browser():
    target = f"http://127.0.0.1:{PORT}/"
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1) as reply:
                if reply.status == 200:
                    webbrowser.open(target)
                    print("Pulse Contracts OS demo opened at", target, flush=True)
                    return
        except Exception:
            time.sleep(0.5)
    print("Server did not become healthy. Check startup messages.", flush=True)


def main():
    home = root()
    data = home / "data"
    data.mkdir(parents=True, exist_ok=True)
    check_demo_data(data)
    # Isolate installed demos from real pilot settings and credentials.
    os.environ["PULSE_DATA_DIR"] = str(data)
    os.environ["PULSE_PILOT_MODE"] = "0"
    os.environ["PULSE_AUTO_BACKUP"] = "1"
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", PORT))
        except OSError as exc:
            raise RuntimeError(
                f"Local demo port {PORT} is already in use. Close the other "
                "Pulse Contracts OS instance and try again."
            ) from exc
    import uvicorn
    from app.main import app
    print("=" * 64)
    print("PULSE CONTRACTS OS — LOCAL FICTIONAL DEMONSTRATION")
    print(f"Version: source build | URL http://127.0.0.1:{PORT}/")
    print("NO live customer data | NO Sicon API credentials required")
    print("DO NOT use this unprotected local demo for real customer records")
    print("Close this window or press Ctrl+C to stop the application.")
    print("=" * 64, flush=True)
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning",
                access_log=False, timeout_keep_alive=10)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\nSTARTUP ERROR:", str(exc), file=sys.stderr, flush=True)
        try:
            input("\nPress Enter to close...")
        except EOFError:
            pass
        sys.exit(1)
