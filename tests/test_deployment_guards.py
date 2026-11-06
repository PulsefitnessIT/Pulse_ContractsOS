"""Release profile rules must fail closed before serving a shared database."""
import pytest
from app.deployment_guards import check_deployment_environment


def staging(**overrides):
    good = {
        "PULSE_DEPLOYMENT_ENV": "staging",
        "PULSE_PILOT_MODE": "1",
        "PULSE_COOKIE_SECURE": "1",
        "PULSE_AUTO_BACKUP": "1",
        "PULSE_SESSION_SECRET": "aZ92!" * 15,
        "PULSE_DATA_DIR": "/mnt/secure_contracts",
        "PULSE_PUBLIC_ORIGIN": "https://contracts.example.org",
    }
    good.update(overrides)
    return good


def test_valid_staging_is_not_misreported_as_production():
    report = check_deployment_environment(staging())
    assert report["deployment_profile"] == "staging"
    assert report["production_certified"] is False
    assert report["public_access_must_be_protected"] is True
    assert "secret" not in report


@pytest.mark.parametrize("overrides",[
    {"PULSE_PILOT_MODE":"0"},
    {"PULSE_COOKIE_SECURE":"0"},
    {"PULSE_SESSION_SECRET":"short"},
    {"PULSE_SESSION_SECRET":"please-replace-this-placeholder-secret-00000000000000"},
    {"PULSE_PUBLIC_ORIGIN":"http://contracts.example.org"},
    {"PULSE_PUBLIC_ORIGIN":"https://contracts.example.org/login"},
    {"PULSE_PUBLIC_ORIGIN":"https://name:password@contracts.example.org"},
    {"PULSE_DATA_DIR":"./local_data"},
    {"PULSE_AUTO_BACKUP":"0"},
])
def test_unsafe_remote_staging_is_rejected_before_bootstrap(overrides):
    with pytest.raises(RuntimeError):
        check_deployment_environment(staging(**overrides))


def test_production_switch_cannot_bypass_security_review():
    with pytest.raises(RuntimeError,match="production launch is blocked"):
        check_deployment_environment(staging(PULSE_DEPLOYMENT_ENV="production"))


def test_development_remains_explicit_and_unapproved():
    report = check_deployment_environment({"PULSE_DEPLOYMENT_ENV":"development"})
    assert report["deployment_profile"]=="development"
    assert report["production_certified"] is False


def test_unknown_runtime_profile_is_not_accepted():
    with pytest.raises(RuntimeError):
        check_deployment_environment({"PULSE_DEPLOYMENT_ENV":"secret-production"})
