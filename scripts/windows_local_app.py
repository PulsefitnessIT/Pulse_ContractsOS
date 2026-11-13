"""Pulse Fitness Contracts OS + SmartQuote — single Windows PC launcher.

Packaged as a single-folder desktop application: no Azure, Docker, Python
installation or network-facing server is necessary for the end user.

It starts the existing FastAPI/SQLite application on *loopback only*, opens
the user's default browser, and offers a small Open / Backup / Stop window.

First launch requires an approved Maintenance Master .xlsx and a named
password-protected local Administrator. No fake customer data is embedded.
The database is NEVER placed in a OneDrive/SharePoint sync folder.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

APP_TITLE = "Pulse Fitness | Contracts OS + SmartQuote"
ROOT_NAME = ("Pulse Fitness", "Contracts OS")
SOURCE_FILE = "approved_master.xlsx"
DATABASE_FILE = "contracts.sqlite3"
SERVICE_HOST = "127.0.0.1"


def local_data_root(env=None):
    variables = os.environ if env is None else env
    base = variables.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise RuntimeError(
            "A Windows LOCALAPPDATA directory is required; the live database "
            "cannot be stored in OneDrive, a network drive or the app folder."
        )
    return Path(base).joinpath(*ROOT_NAME)


def forbid_sync_directory(folder):
    """Reject OneDrive and similar sync roots even for manual overrides."""
    path = Path(folder).absolute()
    for part in path.parts:
        label = part.casefold().replace(" ", "").replace("-", "")
        if any(token in label for token in (
                "onedrive", "dropbox", "googledrive", "iclouddrive")):
            raise ValueError(
                "Choose an ordinary LOCAL drive for the live database. "
                "OneDrive is suitable for separate BACKUP copies only."
            )
    if str(path).startswith("\\\\"):
        raise ValueError("The live database must not use a network share.")
    return path


def _write_secret(path):
    """Create once, exclusively; preserving it retains existing logins."""
    path = Path(path)
    if path.is_file():
        value = path.read_text(encoding="ascii").strip()
        if len(value) < 48:
            raise RuntimeError("Existing session secret is invalid. Ask IT to recover it.")
        return value
    secret_value = secrets.token_urlsafe(64)
    with path.open("x", encoding="ascii") as file:
        file.write(secret_value)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret_value


def _package_self_test():
    """Safe: does not create any accounts, databases or quote records."""
    import fitz  # packaged PDF parser
    import uvicorn
    import lxml
    import tkinter
    # The top-level app is a Python namespace package (no __init__.py),
    # so app.__file__ can legitimately be None in a frozen executable.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    source = base / "app" / "static" / "index.html"
    logo = source.parent / "brand" / "pulse-fitness-reverse.svg"
    if not (source.is_file() and logo.is_file()):
        raise RuntimeError("Bundled Pulse Fitness UI assets are missing.")
    return True


def prepare_environment(data_path, origin, secret):
    folder = forbid_sync_directory(data_path)
    if not folder.is_absolute() or not origin.startswith(
            "http://127.0.0.1:"):
        raise ValueError("Local runtime must use an absolute local folder and loopback.")
    os.environ.update({
        "PULSE_DATA_DIR": str(folder),
        "PULSE_DEPLOYMENT_ENV": "local",
        "PULSE_PILOT_MODE": "1",
        "PULSE_COOKIE_SECURE": "0",  # HTTP only on 127.0.0.1, never over LAN
        "PULSE_PUBLIC_ORIGIN": origin,
        "PULSE_SESSION_SECRET": secret,
        "PULSE_AUTO_BACKUP": "1",
        "PULSE_OCR_MODE": "off",  # OCR requires a separately approved local engine
    })


def _select_first_workbook(root):
    from tkinter import filedialog, messagebox
    messagebox.showinfo(
        APP_TITLE,
        "For the first installation, select Pulse Fitness's approved "
        "Master Maintenance Contracts Excel workbook.\n\n"
        "The workbook is copied into private storage on this PC. "
        "The original file is not changed.",
        parent=root,
    )
    return filedialog.askopenfilename(
        parent=root, title="Select approved Maintenance Master (.xlsx)",
        filetypes=[("Excel workbook", "*.xlsx")],
    )


def ensure_local_data(root, folder):
    """Seed only if *no* live DB exists. Never overwrite existing company data."""
    from tkinter import messagebox
    from app.data_readiness import workbook_check, assess_database
    folder = forbid_sync_directory(folder)
    db = folder / DATABASE_FILE
    master = folder / SOURCE_FILE
    folder.mkdir(parents=True, exist_ok=True)
    if db.is_file() != master.is_file():
        raise RuntimeError(
            "The private database/workbook pair is incomplete. Nothing was "
            "overwritten. Recover both from the approved backup before starting."
        )
    if not db.is_file():
        file = _select_first_workbook(root)
        if not file:
            raise RuntimeError("No Master workbook selected. Setup was cancelled.")
        file_path = Path(file).resolve()
        if file_path.suffix.casefold() != ".xlsx" or file_path.is_symlink():
            raise RuntimeError("Choose an approved .xlsx workbook, not an .xls or link.")
        workbook = workbook_check(file_path)
        if not workbook["valid"]:
            raise RuntimeError(
                "This is not an approved Maintenance Master layout: "
                + "; ".join(workbook["issues"][:4])
            )
        # Human confirmation before importing 9,000+ confidential records:
        # display only aggregate counts; no customer names are sent anywhere.
        from app.source_integrity import source_audit
        audit = source_audit(file_path)
        registers = audit["registers"]
        active = (
            registers.get("Maintenance Database", {}).get("populated_site_rows", 0)
            + registers.get("MOD", {}).get("populated_site_rows", 0)
        )
        expired = registers.get("Expired", {}).get("populated_site_rows", 0)
        approved = messagebox.askyesno(
            APP_TITLE,
            "Confirm that this is the current approved Pulse Fitness Master.\n\n"
            f"Worksheets: {len(audit['worksheet_names'])}\n"
            f"Current commercial/MOD contracts: {active}\n"
            f"Expired archive records: {expired}\n"
            "Five additional source registers (if present) will be kept "
            "as unapproved planning/Sicon evidence.\n\n"
            "The import creates a NEW private database on this PC. "
            "It does not alter the Excel source.\n\n"
            "Are these totals and the workbook version correct?",
            parent=root,
        )
        if not approved:
            raise RuntimeError(
                "The original workbook was not confirmed. No database was imported."
            )
        stage = master.with_suffix(".xlsx.incomplete")
        if stage.exists():
            raise RuntimeError("An interrupted first-run import needs IT review.")
        try:
            with stage.open("xb") as target, file_path.open("rb") as source:
                shutil.copyfileobj(source, target)
            stage.replace(master)
            # Must be imported only AFTER PULSE_DATA_DIR is set.
            from app.store import init_db
            init_db()
        except Exception:
            # Fail closed. Never delete a partial database automatically:
            # doing so could destroy user edits on a subsequent attempt.
            raise RuntimeError(
                "First-run import did not complete. The private data was "
                "retained for IT review; do not delete or overwrite it."
            )
    report = assess_database(db, master)
    if not report["ready_for_data_review"]:
        raise RuntimeError(
            "Maintenance data validation failed. Resolve source errors before "
            "using the app: " + "; ".join(report["issues"][:5])
        )
    if not report["contracts"]["active"]:
        raise RuntimeError("No active contract records found in the approved Master.")
    return report


def ensure_admin(root):
    """Named Admin; no hardcoded credentials or auto-login bypass."""
    import tkinter.simpledialog as prompt
    import tkinter.messagebox as messagebox
    from app.pilot_access import configure_users, provision_user
    from app.store import DB
    configure_users()
    with sqlite3.connect(DB, timeout=10) as connection:
        count = connection.execute(
            "SELECT count(*) FROM pilot_users "
            "WHERE disabled=0 AND role='Admin'"
        ).fetchone()[0]
    if count:
        return
    username = prompt.askstring(
        APP_TITLE, "Create the named local Administrator username "
                   "(3–64 letters/numbers/dots):", parent=root,
    )
    if not username:
        raise RuntimeError("Administrator setup cancelled.")
    first = prompt.askstring(
        APP_TITLE, "Create a strong Administrator password (12+ characters):",
        show="*", parent=root,
    )
    second = prompt.askstring(
        APP_TITLE, "Confirm the Administrator password:",
        show="*", parent=root,
    )
    if not first or first != second:
        raise RuntimeError("The administrator password was not confirmed.")
    provision_user(username, first, "Admin")
    messagebox.showinfo(
        APP_TITLE, "Administrator account created.\n\n"
        "Store the username and password in Pulse's approved password manager. "
        "They are not recoverable from the app.", parent=root,
    )


def _single_instance(lock_file):
    """Hold a Windows-exclusive byte lock while the process remains alive."""
    import msvcrt
    lock = Path(lock_file).open("a+b")
    lock.seek(0, 2)
    if lock.tell() == 0:
        lock.write(b"1")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        return None
    return lock


def _start_loopback_server(sock, error):
    try:
        import uvicorn
        config = uvicorn.Config(
            "app.main:app",
            host=SERVICE_HOST, port=sock.getsockname()[1],
            workers=1, log_level="warning", access_log=False,
            lifespan="on",
        )
        server = uvicorn.Server(config)
        error["server"] = server
        server.run(sockets=[sock])
    except Exception as exc:
        error["failure"] = str(exc)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _wait_for_health(origin, state, timeout=40):
    for _ in range(timeout * 5):
        if state.get("failure"):
            raise RuntimeError("Local application failed: " + state["failure"])
        try:
            with urllib.request.urlopen(origin + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError(
        "The app did not start successfully. Check the approved private "
        "workbook and contact Pulse IT."
    )


def launch():
    import tkinter as tk
    from tkinter import messagebox
    if sys.platform != "win32":
        raise RuntimeError("This launcher is only intended for Windows.")
    data_root = local_data_root()
    folder = forbid_sync_directory(data_root / "data")
    data_root.mkdir(parents=True, exist_ok=True)
    lock = _single_instance(data_root / "app-instance.lock")
    port_file = data_root / "active-port.txt"
    if lock is None:
        # Existing running instance: never open two writers on the DB.
        try:
            port = int(port_file.read_text().strip())
            if 1 <= port <= 65535:
                webbrowser.open(f"http://127.0.0.1:{port}/")
        except (ValueError, OSError):
            pass
        return 0

    root = tk.Tk()
    root.withdraw()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind((SERVICE_HOST, 0))  # loopback ONLY, random private port
        sock.listen(128)
        port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        secret = _write_secret(data_root / "session.secret")
        prepare_environment(folder, origin, secret)
        ensure_local_data(root, folder)
        ensure_admin(root)
        state = {}
        background = threading.Thread(
            target=_start_loopback_server,
            args=(sock, state), daemon=True, name="Pulse Local Engine",
        )
        background.start()
        _wait_for_health(origin, state)
        port_file.write_text(str(port), encoding="ascii")
        root.title(APP_TITLE)
        root.geometry("390x230")
        root.resizable(False, False)
        root.configure(background="#1B1C1D")
        heading = tk.Label(
            root, text="PULSE FITNESS", fg="#19CDFF", bg="#1B1C1D",
            font=("Arial", 19, "bold"),
        )
        heading.pack(pady=(17, 4))
        tk.Label(
            root, text="Contracts OS + SmartQuote — running on this PC",
            fg="white", bg="#1B1C1D", font=("Arial", 10),
        ).pack(pady=(0, 12))
        tk.Button(
            root, text="Open Contracts OS + SmartQuote",
            command=lambda: webbrowser.open(origin + "/"),
            width=33,
        ).pack(pady=4)

        def backup_now():
            from app.backups import create_local_backup
            try:
                outcome = create_local_backup(force=True)
                messagebox.showinfo(
                    APP_TITLE,
                    "Local backup completed:\n"
                    + outcome["filename"] + "\n\n"
                    "Copy approved backup files off this PC using Pulse's "
                    "secure backup policy. Do not move the LIVE database.",
                    parent=root,
                )
            except Exception as exc:
                messagebox.showerror(APP_TITLE, "Backup failed: " + str(exc), parent=root)

        tk.Button(root, text="Create local backup", command=backup_now,
                  width=33).pack(pady=4)

        def stop():
            server = state.get("server")
            if server:
                server.should_exit = True
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", stop)
        root.deiconify()
        webbrowser.open(origin + "/")
        root.mainloop()
        return 0
    except Exception as exc:
        messagebox.showerror(
            APP_TITLE,
            "Contracts OS could not open:\n\n" + str(exc)
            + "\n\nExisting company data has not been overwritten.",
            parent=root,
        )
        return 2
    finally:
        server = locals().get("state", {}).get("server")
        if server is not None:
            server.should_exit = True
        try:
            sock.close()
        except OSError:
            pass
        if lock is not None:
            lock.close()
        try:
            port_file.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            root.destroy()
        except Exception:
            pass


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ["--self-test"]:
        return 0 if _package_self_test() else 2
    if args:
        raise SystemExit("No arguments needed. Double-click the Windows app.")
    return launch()


if __name__ == "__main__":
    sys.exit(main())
