#!/usr/bin/env python3
"""Prepare a reviewable, source-only copy of the V12 pilot ZIP.
This script NEVER publishes or commits to GitHub. Review all output before copying.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

BLOCKED_PARTS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    "data", "uploads", "invoices", "documents", "backups",
    "exports", "storage", "runtime", "generated", "secrets",
    "credentials", "customer_data", "private",
}
BLOCKED_EXTS = {
    ".zip", ".7z", ".rar", ".pdf", ".xlsx", ".xls", ".xlsm",
    ".csv", ".docx", ".eml", ".db", ".sqlite", ".sqlite3",
    ".bak", ".pem", ".key", ".pfx", ".p12", ".png",
    ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".webp",
    ".exe", ".dll", ".so", ".pkl", ".pickle", ".parquet",
}
ALLOWED_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css",
    ".scss", ".json", ".toml", ".yaml", ".yml", ".ini",
    ".md", ".txt", ".sh", ".bat", ".ps1", ".xml",
}
ALLOWED_NAMES = {"dockerfile", "makefile", ".gitignore", ".dockerignore"}
PATTERNS = {
    "credential assignment": re.compile(
        r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[=:]\s*[\x27\x22][^\x27\x22\s]{8,}"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "likely customer email": re.compile(
        r"(?i)[A-Z0-9._%+-]+@(?!example\.(?:com|org|net))[-A-Z0-9.]+\.[A-Z]{2,}"
    ),
    "sample customer reference": re.compile(r"(?i)university of huddersfield|daphne steele"),
}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="V12 ZIP file downloaded from the conversation")
    parser.add_argument("output", type=Path, help="New EMPTY directory outside the repository")
    args = parser.parse_args()
    archive = args.archive.resolve()
    output = args.output.resolve()
    if not archive.is_file():
        parser.error("The V12 archive does not exist.")
    if output.exists() and any(output.iterdir()):
        parser.error("The output directory must be empty. No existing files will be overwritten.")
    if output == archive.parent or str(output).startswith(str(archive.parent / ".git")):
        parser.error("Choose a separate staging directory.")
    output.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    skipped: list[dict[str, str]] = []
    flagged: list[dict[str, str]] = []
    total_size = 0
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            if item.is_dir():
                continue
            posix = PurePosixPath(item.filename.replace("\\", "/"))
            parts = posix.parts
            if not parts or posix.is_absolute() or ".." in parts:
                skipped.append({"path": item.filename, "reason": "unsafe path"})
                continue
            rel = Path(*parts)
            if any(p.lower() in BLOCKED_PARTS for p in parts):
                skipped.append({"path": str(rel), "reason": "blocked directory"})
                continue
            if any(p.lower().startswith(".env") for p in parts) or "credential" in rel.name.lower():
                skipped.append({"path": str(rel), "reason": "possible secret"})
                continue
            if stat.S_ISLNK(item.external_attr >> 16):
                skipped.append({"path": str(rel), "reason": "symlink"})
                continue
            ext = rel.suffix.lower()
            if ext in BLOCKED_EXTS or not (ext in ALLOWED_EXTS or rel.name.lower() in ALLOWED_NAMES):
                skipped.append({"path": str(rel), "reason": "non-source file"})
                continue
            if item.file_size > 10_000_000:
                skipped.append({"path": str(rel), "reason": "unexpectedly large source file"})
                continue
            total_size += item.file_size
            if total_size > 150_000_000:
                raise ValueError("Source material exceeds safety limit.")
            raw = source.read(item)
            try:
                contents = raw.decode("utf-8")
            except UnicodeDecodeError:
                skipped.append({"path": str(rel), "reason": "non-UTF8 file"})
                continue
            reasons = [name for name, regex in PATTERNS.items() if regex.search(contents)]
            if reasons:
                flagged.append({"path": str(rel), "reason": ", ".join(reasons)})
                continue
            dest = (output / rel).resolve()
            if not dest.is_relative_to(output):
                skipped.append({"path": str(rel), "reason": "escaped staging directory"})
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(contents, encoding="utf-8")
            kept.append(str(rel))
    report = {
        "archive": archive.name, "copied": kept, "skipped": skipped, "flagged": flagged,
        "status": "manual review required before Git commit",
    }
    (output / "MIGRATION_REVIEW.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Staged {len(kept)} source files; skipped {len(skipped)}; flagged {len(flagged)}.")
    print(f"Review directory: {output}")
    print("Important: DO NOT commit MIGRATION_REVIEW.json or any flagged material without review.")

if __name__ == "__main__":
    main()
