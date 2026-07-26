# -*- coding: utf-8 -*-
"""Regression coverage for the no-SSH website deployment fallback."""

import importlib.util
import pathlib
import ssl
import urllib.error

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "deploy_website_cloud_assistant.py"
SPEC = importlib.util.spec_from_file_location("deploy_website_cloud_assistant", SCRIPT_PATH)
assert SPEC and SPEC.loader
cloud_assistant = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cloud_assistant)


def test_signed_params_keeps_secret_out_of_request_values():
    params = cloud_assistant.signed_params(
        "RunCommand",
        {"RegionId": "cn-hangzhou", "InstanceId.1": "i-example"},
        "test-access-key",
        "test-secret",
    )

    assert params["Action"] == "RunCommand"
    assert params["SignatureMethod"] == "HMAC-SHA1"
    assert params["SignatureVersion"] == "1.0"
    assert params["AccessKeyId"] == "test-access-key"
    assert "test-secret" not in params.values()
    assert params["Signature"]


def test_deployment_script_is_tagged_atomic_and_rolls_back():
    script = cloud_assistant.deployment_script("0.8.2")

    assert "refs/tags/v${version}.tar.gz" in script
    assert "Guanlan v${version}" in script
    assert "previous=" in script
    assert "if ! systemctl reload nginx; then" in script
    assert 'ln -sfn "$previous" "$current"' in script
    assert "curl -fsS --connect-timeout 8 http://127.0.0.1/" in script


@pytest.mark.parametrize("version", ["0.8", "v0.8.2", "0.8.2;rm -rf /", "0.8.2\nwhoami"])
def test_deployment_script_rejects_non_release_versions(version):
    with pytest.raises(cloud_assistant.CloudAssistantError):
        cloud_assistant.deployment_script(version)


def test_missing_credentials_fail_before_any_api_call(monkeypatch):
    monkeypatch.delenv("GUANLAN_ALIYUN_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("GUANLAN_ALIYUN_ACCESS_KEY_SECRET", raising=False)

    with pytest.raises(cloud_assistant.CloudAssistantError, match="GUANLAN_ALIYUN_ACCESS_KEY_ID"):
        cloud_assistant.deploy("0.8.2", timeout_seconds=30)


def test_api_request_uses_system_curl_for_a_local_python_tls_error(monkeypatch):
    def raise_tls_error(*_args, **_kwargs):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("local CA unavailable"))

    monkeypatch.setattr(cloud_assistant.urllib.request, "urlopen", raise_tls_error)
    monkeypatch.setattr(cloud_assistant, "curl_get", lambda _url: '{"InvokeId":"t-example"}')

    payload = cloud_assistant.api_request("https://ecs.aliyuncs.com/", {"Action": "RunCommand"})

    assert payload == {"InvokeId": "t-example"}


def test_deploy_submits_tagged_command_and_polls_until_success(monkeypatch, capsys):
    monkeypatch.setenv("GUANLAN_ALIYUN_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("GUANLAN_ALIYUN_ACCESS_KEY_SECRET", "test-access-secret")
    requests = []

    def fake_api_request(_endpoint, params):
        requests.append(params)
        if params["Action"] == "RunCommand":
            return {"InvokeId": "t-example"}
        return {
            "Invocations": {
                "Invocation": [{"InvocationStatus": "Success", "ExitCode": "0"}]
            }
        }

    monkeypatch.setattr(cloud_assistant, "api_request", fake_api_request)
    monkeypatch.setattr(cloud_assistant.time, "sleep", lambda _seconds: None)

    cloud_assistant.deploy("0.8.2", timeout_seconds=30)

    run_command, describe = requests
    assert run_command["Action"] == "RunCommand"
    assert run_command["InstanceId.1"] == cloud_assistant.DEFAULT_INSTANCE_ID
    decoded_script = cloud_assistant.base64.b64decode(run_command["CommandContent"]).decode("utf-8")
    assert "refs/tags/v${version}.tar.gz" in decoded_script
    assert describe["Action"] == "DescribeInvocations"
    assert describe["InvokeId"] == "t-example"
    assert "website deployment completed via Cloud Assistant" in capsys.readouterr().out


def test_deploy_reports_failed_command_status_without_printing_signed_request(monkeypatch):
    monkeypatch.setenv("GUANLAN_ALIYUN_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("GUANLAN_ALIYUN_ACCESS_KEY_SECRET", "test-access-secret")

    def fake_api_request(_endpoint, params):
        if params["Action"] == "RunCommand":
            return {"InvokeId": "t-example"}
        return {
            "Invocations": {
                "Invocation": [
                    {
                        "InvocationStatus": "Failed",
                        "ExitCode": "1",
                        "Output": "nginx configuration check failed",
                    }
                ]
            }
        }

    monkeypatch.setattr(cloud_assistant, "api_request", fake_api_request)
    monkeypatch.setattr(cloud_assistant.time, "sleep", lambda _seconds: None)

    with pytest.raises(cloud_assistant.CloudAssistantError, match="status=Failed, exit_code=1") as exc:
        cloud_assistant.deploy("0.8.2", timeout_seconds=30)

    assert "test-access-secret" not in str(exc.value)
