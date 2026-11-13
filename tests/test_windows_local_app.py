"""Local Windows app packaging and security profiles, with NO real data."""
from pathlib import Path
import os

import pytest

from app.deployment_guards import check_deployment_environment
from app.pilot_access import _public_origin_is_allowed
from scripts.windows_local_app import (
    forbid_sync_directory, local_data_root, prepare_environment, _write_secret,
)


def local_env(tmp_path):
    return {
        "PULSE_DEPLOYMENT_ENV": "local",
        "PULSE_PILOT_MODE": "1",
        "PULSE_COOKIE_SECURE": "0",
        "PULSE_AUTO_BACKUP": "1",
        "PULSE_DATA_DIR": str(tmp_path / "Pulse Fitness" / "Contracts OS" / "data"),
        "PULSE_PUBLIC_ORIGIN": "http://127.0.0.1:59428",
        "PULSE_SESSION_SECRET": "a" * 65,
    }


def test_local_desktop_rejects_sync_folders_and_network_paths(tmp_path):
    for path in (
        tmp_path / "OneDrive - Pulse Fitness" / "Contracts OS",
        tmp_path / "Dropbox" / "Contracts OS",
        tmp_path / "Google Drive" / "Contracts OS",
    ):
        with pytest.raises(ValueError):
            forbid_sync_directory(path)
    assert forbid_sync_directory(tmp_path / "Pulse Fitness" / "Contracts OS")


def test_windows_user_local_data_path_is_not_onedrive(tmp_path):
    env={"LOCALAPPDATA":str(tmp_path / "AppData" / "Local")}
    target=local_data_root(env)
    assert target == tmp_path / "AppData" / "Local" / "Pulse Fitness" / "Contracts OS"
    with pytest.raises(RuntimeError):
        local_data_root({"LOCALAPPDATA":""})


def test_local_session_secret_is_random_but_stable(tmp_path):
    target=tmp_path/"session.secret"
    first=_write_secret(target)
    again=_write_secret(target)
    assert len(first)>=48
    assert first==again
    assert target.read_text()==first
    assert len(first)!=0


def test_local_profile_is_independent_from_remote_staging(tmp_path):
    env=local_env(tmp_path)
    result=check_deployment_environment(env)
    assert result["deployment_profile"]=="local"
    assert result["public_access_must_be_protected"] is True
    assert result["production_certified"] is False


@pytest.mark.parametrize("change", [
    {"PULSE_PILOT_MODE":"0"},
    {"PULSE_COOKIE_SECURE":"1"},
    {"PULSE_AUTO_BACKUP":"0"},
    {"PULSE_SESSION_SECRET":"short"},
    {"PULSE_PUBLIC_ORIGIN":"http://0.0.0.0:59428"},
    {"PULSE_PUBLIC_ORIGIN":"http://localhost:59428"},
    {"PULSE_PUBLIC_ORIGIN":"https://127.0.0.1:59428"},
    {"PULSE_PUBLIC_ORIGIN":"http://127.0.0.1"},
    {"PULSE_PUBLIC_ORIGIN":"http://127.0.0.1:59428/other"},
    {"PULSE_DATA_DIR":"OneDrive/Contracts OS"},
])
def test_unsafe_local_runtime_profiles_fail_closed(tmp_path,change):
    env=local_env(tmp_path)
    env.update(change)
    with pytest.raises(RuntimeError):
        check_deployment_environment(env)


def test_local_csrf_origin_requires_matching_loopback_origin(monkeypatch,tmp_path):
    env=local_env(tmp_path)
    for key,value in env.items():
        monkeypatch.setenv(key,value)
    assert _public_origin_is_allowed(
        {"origin":"http://127.0.0.1:59428"}
    )
    assert _public_origin_is_allowed(
        {"referer":"http://127.0.0.1:59428/quoting"}
    )
    assert not _public_origin_is_allowed(
        {"origin":"http://localhost:59428"}
    )
    assert not _public_origin_is_allowed(
        {"origin":"http://127.0.0.1:8000"}
    )
    assert not _public_origin_is_allowed(
        {"origin":"https://evil.example.invalid"}
    )


def test_launcher_uses_protected_local_profile_without_writes(
        tmp_path,monkeypatch):
    env=local_env(tmp_path)
    for name in (
        "PULSE_SESSION_SECRET","PULSE_PUBLIC_ORIGIN","PULSE_DATA_DIR",
        "PULSE_PILOT_MODE","PULSE_COOKIE_SECURE","PULSE_DEPLOYMENT_ENV",
        "PULSE_AUTO_BACKUP"
    ):
        monkeypatch.delenv(name,raising=False)
    prepare_environment(
        Path(env["PULSE_DATA_DIR"]),
        env["PULSE_PUBLIC_ORIGIN"],
        env["PULSE_SESSION_SECRET"],
    )
    assert check_deployment_environment()["deployment_profile"]=="local"
    assert os.getenv("PULSE_PILOT_MODE")=="1"
    assert os.getenv("PULSE_COOKIE_SECURE")=="0"
    assert os.getenv("PULSE_OCR_MODE")=="off"
    assert not Path(env["PULSE_DATA_DIR"]).exists()
