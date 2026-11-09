"""Fail-closed guardrails for remotely hosted Contracts OS staging.

Deliberately does not certify production security. Live production remains
blocked until central identity, backup/restore, reconciliation and independent
security acceptance are implemented and signed off.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

ENV_NAME = "PULSE_DEPLOYMENT_ENV"
APPROVED_PROFILES = {"development", "local", "staging", "production"}
_PLACEHOLDER_MARKERS = ("changeme", "placeholder", "replace", "example", "not-a-secret")


def check_deployment_environment(values=None):
    """Returns a public-safe profile; never returns or logs secret values."""
    env = os.environ if values is None else values
    profile = (env.get(ENV_NAME) or "development").strip().lower()
    if profile not in APPROVED_PROFILES:
        raise RuntimeError("PULSE_DEPLOYMENT_ENV must be development, local, staging or production.")

    if profile == "production":
        # This branch still uses pilot accounts with no central MFA or
        # independently assessed role/security controls. Do not let anyone
        # rename staging to production via one environment variable.
        raise RuntimeError(
            "Contracts OS production launch is blocked in this release. "
            "Complete central identity/MFA, external security assessment, "
            "backup-restore drills, real Master reconciliation and signed "
            "production release gates before enabling production."
        )

    if profile == "local":
        # Single-user Windows desktop mode. No remote server, no data in
        # OneDrive and no cookie-security downgrade for shared staging.
        from urllib.parse import urlsplit
        if env.get("PULSE_PILOT_MODE") != "1":
            raise RuntimeError("Local desktop must use named pilot login.")
        if env.get("PULSE_COOKIE_SECURE") != "0":
            raise RuntimeError("Loopback HTTP requires a local-only cookie profile.")
        secret = env.get("PULSE_SESSION_SECRET", "")
        if len(secret) < 48 or any(m in secret.lower() for m in _PLACEHOLDER_MARKERS):
            raise RuntimeError("Local desktop requires a unique long session secret.")
        directory = env.get("PULSE_DATA_DIR", "")
        if not directory or not Path(directory).is_absolute():
            raise RuntimeError("Local desktop requires an absolute private data path.")
        if any("onedrive" in section.casefold() or section.casefold() in
               {"dropbox", "google drive", "icloud drive"}
               for section in Path(directory).parts):
            raise RuntimeError(
                "The live Contracts OS SQLite database cannot be in a sync folder."
            )
        public = env.get("PULSE_PUBLIC_ORIGIN", "")
        try:
            origin = urlsplit(public)
            if (origin.scheme != "http" or origin.hostname != "127.0.0.1"
                    or origin.port is None or not 1 <= origin.port <= 65535
                    or origin.path not in ("", "/") or origin.username
                    or origin.password or origin.query or origin.fragment):
                raise ValueError("Invalid loopback origin")
        except ValueError as exc:
            raise RuntimeError(
                "Local desktop must use http://127.0.0.1:<ephemeral-port> only."
            ) from exc
        if env.get("PULSE_AUTO_BACKUP", "1") != "1":
            raise RuntimeError("Local desktop must keep local backup checkpoints.")

    if profile == "staging":
        if env.get("PULSE_PILOT_MODE") != "1":
            raise RuntimeError("Server staging requires PULSE_PILOT_MODE=1; demo mode is not allowed.")
        if env.get("PULSE_COOKIE_SECURE") != "1":
            raise RuntimeError("Server staging requires secure-only authentication cookies.")
        secret = env.get("PULSE_SESSION_SECRET", "")
        if len(secret) < 48 or any(m in secret.lower() for m in _PLACEHOLDER_MARKERS):
            raise RuntimeError(
                "Server staging requires a unique high-entropy session signing "
                "secret of at least 48 characters from the server secret store."
            )
        data = env.get("PULSE_DATA_DIR", "")
        if not data or not Path(data).is_absolute():
            raise RuntimeError("Server staging requires an absolute, private PULSE_DATA_DIR.")
        public = env.get("PULSE_PUBLIC_ORIGIN", "")
        try:
            parts = urlsplit(public)
        except ValueError as exc:
            raise RuntimeError("Server staging requires one validated public HTTPS origin.") from exc
        if (parts.scheme != "https" or not parts.hostname or parts.username or
            parts.password or parts.query or parts.fragment or
            parts.path not in ("", "/")):
            raise RuntimeError(
                "PULSE_PUBLIC_ORIGIN must be the HTTPS origin only, "
                "for example https://contracts.internal.example."
            )
        # Refuse to disable standard protection while preparing a shared
        # server. Actual web-access and trusted TLS configuration need a
        # separate operational test by IT.
        if env.get("PULSE_AUTO_BACKUP", "1") == "0":
            raise RuntimeError("Staging must not disable local recovery checkpoints.")
    return {"deployment_profile": profile, "production_certified": False,
            "public_access_must_be_protected": profile in ("staging", "local")}
