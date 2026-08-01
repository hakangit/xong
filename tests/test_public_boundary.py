import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_public_boundary.py"
_SPEC = importlib.util.spec_from_file_location("check_public_boundary", _SCRIPT)
assert _SPEC and _SPEC.loader
check_public_boundary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_public_boundary)


def test_flags_private_network_and_contact_data():
    text = "\n".join(
        (
            "host=" + "10" + ".24.3.8",
            "owner=person@" + "company" + ".com",
            "database=db." + "corp",
        )
    )

    assert check_public_boundary.content_violations(text) == [
        "non-example email address",
        "private DNS name",
        "private IPv4 address",
    ]


def test_allows_reserved_examples_and_loopback():
    text = "192.0.2.10 198.51.100.20 203.0.113.30 127.0.0.1 user@example.com"

    assert check_public_boundary.content_violations(text) == []


def test_private_denylist_does_not_echo_the_matching_value():
    value = "private" + "tenant"

    assert check_public_boundary.content_violations(
        "tenant=" + value, (value,)
    ) == ["private denylist match"]


def test_rejects_private_deployment_artifacts():
    assert check_public_boundary.path_violations(Path("deploy/service.nomad.hcl")) == [
        "private deployment path",
        "sensitive file type",
    ]
    assert check_public_boundary.path_violations(Path("docs/example.md")) == []
