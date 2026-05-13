import json
from pathlib import Path

from guanlan import openguanlan_cli


def test_openguanlan_capabilities_are_browser_assist_scoped(capsys):
    exit_code = openguanlan_cli.main(["capabilities", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 0
    assert "state" in data["absorbed_opencli_primitives"]
    assert "find" in data["absorbed_opencli_primitives"]
    assert "screenshot" in data["absorbed_opencli_primitives"]
    assert any("click/type/fill" in item for item in data["excluded_opencli_primitives"])
    assert any("cookie/token" in item for item in data["excluded_opencli_primitives"])
    assert data["privacy_boundary"] == "browser-assist user-authorized target visible page only"


def test_openguanlan_setup_points_to_packaged_extension(capsys):
    exit_code = openguanlan_cli.main(["setup", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    extension_path = Path(data["path"])
    assert exit_code == 0
    assert data["status"] == "manual_extension_step_required"
    assert (extension_path / "manifest.json").exists()
    assert data["safety"]["credential_material_access_allowed"] is False
    assert data["safety"]["extension_install_requires_user_confirmation"] is True


def test_openguanlan_doctor_supports_subcommand_json_and_port(capsys):
    exit_code = openguanlan_cli.main(["doctor", "--json", "--port", "9"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 0
    assert data["status"] == "needs_daemon"
    assert data["daemon"]["port"] == 9
    assert data["extension"]["exists"] is True
    assert data["safety"]["credential_material_access_allowed"] is False


def test_openguanlan_read_visible_fails_closed_without_daemon(capsys):
    exit_code = openguanlan_cli.main(
        ["read-visible", "https://example.com", "--timeout", "0.1", "--port", "9"]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 69
    assert data["status"] == "bridge_unavailable"
    assert data["setup"]["safety"]["credential_material_access_allowed"] is False


def test_openguanlan_extension_manifest_does_not_request_credential_permissions():
    manifest_path = Path(openguanlan_cli._extension_payload()["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    permissions = set(manifest["permissions"])
    assert {"activeTab", "scripting", "tabs"} <= permissions
    assert "cookies" not in permissions
    assert "storage" not in permissions
    assert "debugger" not in permissions
