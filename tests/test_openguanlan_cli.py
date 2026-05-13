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
    assert (extension_path / "popup.html").exists()
    assert data["safety"]["credential_material_access_allowed"] is False
    assert data["safety"]["extension_install_requires_user_confirmation"] is True
    assert data["safety"]["site_permission_requires_user_confirmation"] is True
    assert data["chrome_store"]["package_command"] == "scripts/build_openguanlan_extension.sh"
    assert data["pairing"]["pair_code_command"] == "openguanlan pair-code --json"


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


def test_openguanlan_pair_code_creates_local_auth_state(capsys, tmp_path, monkeypatch):
    auth_path = tmp_path / "bridge-auth.json"
    monkeypatch.setattr(openguanlan_cli, "_bridge_auth_path", lambda: auth_path)

    exit_code = openguanlan_cli.main(["pair-code", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 0
    assert data["status"] == "pair_code_ready"
    assert data["pairing_token"]
    assert data["auth_path"] == str(auth_path)
    saved = json.loads(auth_path.read_text(encoding="utf-8"))
    assert saved["pairing_token"] == data["pairing_token"]
    assert saved["session_token"]


def test_openguanlan_pair_reset_rotates_pairing_token(capsys, tmp_path, monkeypatch):
    auth_path = tmp_path / "bridge-auth.json"
    monkeypatch.setattr(openguanlan_cli, "_bridge_auth_path", lambda: auth_path)
    first = openguanlan_cli._bridge_auth_state(create=True)

    exit_code = openguanlan_cli.main(["pair-reset", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    saved = json.loads(auth_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert data["status"] == "pair_code_rotated"
    assert data["pairing_token"] != first["pairing_token"]
    assert saved["pairing_token"] == data["pairing_token"]
    assert saved["session_token"] == first["session_token"]


def test_openguanlan_extension_manifest_does_not_request_credential_permissions():
    manifest_path = Path(openguanlan_cli._extension_payload()["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    background = (manifest_path.parent / "background.js").read_text(encoding="utf-8")
    popup = (manifest_path.parent / "popup.html").read_text(encoding="utf-8")

    permissions = set(manifest["permissions"])
    assert {"activeTab", "scripting", "tabs"} <= permissions
    assert "cookies" not in permissions
    assert "storage" not in permissions
    assert "debugger" not in permissions
    assert "<all_urls>" not in set(manifest.get("host_permissions", []))
    assert "<all_urls>" in set(manifest.get("optional_host_permissions", []))
    assert manifest["action"]["default_popup"] == "popup.html"
    assert 'const PAIRING_HEADER = "x-openguanlan-pairing";' in background
    assert 'message.type === "openguanlan:set-pairing-token"' in background
    assert "Pair Code" in popup
    assert 'if (task.action === "get_title") {\n    await ensureSitePermission(tab.url);' in background
    assert "async function screenshot(task) {\n  const tab = await ensureTab(task, { navigate: false });\n  await ensureSitePermission(tab.url);" in background
