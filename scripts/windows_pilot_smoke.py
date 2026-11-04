"""Exercise the FROZEN Windows EXE from bootstrap through authenticated SmartQuote.

Only fictional minimal Excel and a fictional Admin are used. The executable
cannot access real customer files during this GitHub Actions acceptance run.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_ten_tab_master import create_ten_tab_file


def run():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/windows_pilot_smoke.py PATH_TO_EXE")
    executable = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="fictional-smartquote-pilot-") as temp:
        folder = Path(temp)
        portable = folder / executable.name
        shutil.copy2(executable, portable)
        master = folder / "Fictional_Current_Master.xlsx"
        create_ten_tab_file(master)

        boot = subprocess.run(
            [str(portable), "--bootstrap-master", str(master)],
            input="APPROVED\n", capture_output=True, text=True,
            timeout=130, cwd=folder
        )
        if boot.returncode:
            raise AssertionError(
                "Frozen Windows first-run bootstrap failed: "
                + boot.stdout[-1500:] + boot.stderr[-1500:]
            )
        private = folder / "private_runtime"
        assert (private / "approved_master.xlsx").is_file()
        assert (private / "contracts.sqlite3").is_file()
        with sqlite3.connect(private / "contracts.sqlite3") as db:
            rows = db.execute(
                "SELECT status,COUNT(*) FROM contracts GROUP BY status"
            ).fetchall()
            assert dict(rows)["Active"] == 2, rows
            assert dict(rows)["Expired"] == 1, rows

        not_ready = subprocess.run(
            [str(portable), "--has-admin"],
            capture_output=True, text=True, timeout=35, cwd=folder
        )
        assert not_ready.returncode == 1, not_ready.stderr

        env = dict(os.environ)
        env["PULSE_DATA_DIR"] = str(private)
        sys.path.insert(0, str(ROOT))
        from app import pilot_access
        from app import store
        store.DATA = str(private)
        store.DB = str(private / "contracts.sqlite3")
        pilot_access.DB = store.DB
        pilot_access.DATA = store.DATA
        pilot_access.provision_user(
            "fictional-admin", "fictional-password-2026!",
            "Admin"
        )
        ready = subprocess.run(
            [str(portable), "--has-admin"],
            capture_output=True, text=True, timeout=35, cwd=folder
        )
        assert ready.returncode == 0, ready.stderr

        logs = folder / "server-output.txt"
        with logs.open("w+", encoding="utf-8") as logfile:
            proc = subprocess.Popen(
                [str(portable), "--serve"],
                stdout=logfile, stderr=subprocess.STDOUT,
                cwd=folder
            )
            try:
                server = "http://127.0.0.1:18080"
                browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
                failure = None
                for attempt in range(70):
                    try:
                        with browser.open(server + "/api/health", timeout=3) as response:
                            if response.status == 200 and json.load(response)["status"] == "ok":
                                break
                    except Exception as exc:
                        failure = exc
                        if proc.poll() is not None:
                            raise RuntimeError(
                                "Frozen Windows pilot exited before liveness: "
                                + logs.read_text(encoding="utf-8")[-2000:]
                            ) from exc
                        time.sleep(1)
                else:
                    raise RuntimeError("Frozen Windows pilot never became live: " + str(failure))
                with browser.open(server + "/", timeout=5) as response:
                    assert response.status == 200
                payload = json.dumps({
                    "username": "fictional-admin",
                    "password": "fictional-password-2026!"
                }).encode()
                request = Request(
                    server + "/api/pilot/login", data=payload,
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with browser.open(request, timeout=8) as response:
                    assert json.load(response)["role"] == "Admin"
                with browser.open(server + "/api/quoting/release-check", timeout=10) as response:
                    status = json.load(response)
                    assert status["required_ready"] is False
                    assert status["customer_quote_requires_per_draft_admin_approval"]
                print(
                    "PASS: frozen Windows EXE bootstraps fictional Excel, "
                    "preserves all three register rows, provisions named Admin, "
                    "serves loopback app, logs in and refuses unapproved quoting."
                )
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == "__main__":
    run()
