from pathlib import Path

import helpers.credentials as credentials
import helpers.deploy_helpers as deploy_helpers
import pytest
import refresh


def create_profile_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    config_dir = tmp_path / "config"
    workspace_dir = tmp_path / "workspace" / "finance"
    config_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    for name in (
        "Shared.SemanticModel",
        "Finance.SemanticModel",
        "ReportA.Report",
        "ReportB.Report",
        "Unresolved.Report",
    ):
        (workspace_dir / name).mkdir()
    (workspace_dir / "Shared.SemanticModel" / ".platform").write_text(
        '{"metadata": {"displayName": "Shared"}}\n'
    )
    (workspace_dir / "Finance.SemanticModel" / ".platform").write_text(
        '{"metadata": {"displayName": "Finance"}}\n'
    )
    (workspace_dir / "ReportA.Report" / "definition.pbir").write_text(
        '{"datasetReference": {"byPath": {"path": "../Shared.SemanticModel"}}}\n'
    )
    (workspace_dir / "ReportB.Report" / "definition.pbir").write_text(
        '{"datasetReference": {"byPath": {"path": "../Finance.SemanticModel"}}}\n'
    )
    (workspace_dir / "Unresolved.Report" / "definition.pbir").write_text(
        '{"datasetReference": {}}\n'
    )
    (config_dir / "config-finance.yml").write_text(
        "core:\n"
        "  workspace_id:\n"
        "    dev: dev-workspace\n"
        "    test: test-workspace\n"
        "    prod: prod-workspace\n"
        "  repository_directory: ../workspace/finance\n"
        "  parameter: ./parameter-finance.yml\n"
        "  item_types_in_scope:\n"
        "    - SemanticModel\n"
        "    - Report\n"
    )
    (config_dir / "parameter-finance.yml").write_text("find_replace: []\n")
    manifest = config_dir / "profiles.yml"
    manifest.write_text(
        "profiles:\n"
        "  - name: finance\n"
        "    enabled: true\n"
        "    config: config-finance.yml\n"
        "    refresh: trigger\n"
    )
    return config_dir, workspace_dir, manifest


def patch_fixture_paths(tmp_path, monkeypatch):
    config_dir, workspace_dir, manifest = create_profile_fixture(tmp_path)
    monkeypatch.setattr(deploy_helpers, "root_directory", tmp_path)
    monkeypatch.setattr(deploy_helpers, "config_directory", config_dir)
    monkeypatch.setattr(deploy_helpers, "profiles_path", manifest)
    return workspace_dir


def test_profile_manifest_selects_only_enabled_profiles(tmp_path, monkeypatch):
    patch_fixture_paths(tmp_path, monkeypatch)
    assert deploy_helpers.discover_profiles() == ["finance"]
    assert deploy_helpers.get_profile_definition("finance").refresh_mode == "trigger"


def test_scope_expands_reports_for_semantic_model_change(tmp_path, monkeypatch):
    patch_fixture_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(deploy_helpers, "get_changed_paths", lambda *args: [])
    monkeypatch.setattr(
        deploy_helpers,
        "get_changed_items",
        lambda *args, **kwargs: ["Shared.SemanticModel"],
    )
    scope = deploy_helpers.resolve_deployment_scope("finance", "baseline")
    assert scope.should_deploy is True
    assert scope.full_deploy is False
    assert set(scope.changed_items or []) == {
        "Shared.SemanticModel",
        "ReportA.Report",
        "Unresolved.Report",
    }


def test_scope_uses_full_deploy_for_parameter_change(tmp_path, monkeypatch):
    patch_fixture_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(
        deploy_helpers,
        "get_changed_paths",
        lambda *args: ["config/parameter-finance.yml"],
    )
    scope = deploy_helpers.resolve_deployment_scope("finance", "baseline")
    assert scope.should_deploy is True
    assert scope.full_deploy is True
    assert scope.changed_items is None


def test_no_explicit_baseline_is_safe_full_deploy(tmp_path, monkeypatch):
    patch_fixture_paths(tmp_path, monkeypatch)
    scope = deploy_helpers.resolve_deployment_scope("finance")
    assert scope.full_deploy is True
    assert "safe full profile deploy" in scope.reason


def test_client_secret_requires_environment_variables(monkeypatch):
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="AZURE_TENANT_ID"):
        credentials.get_token_credential("client_secret")


def test_trigger_refresh_returns_request_id(monkeypatch):
    class Response:
        status_code = 202
        headers = {"x-ms-request-id": "refresh-123"}
        text = ""
        reason = "Accepted"

    monkeypatch.setattr(refresh.requests, "post", lambda *args, **kwargs: Response())
    assert (
        refresh.trigger_refresh("workspace", "dataset", "Model", {"Authorization": "x"})
        == "refresh-123"
    )


def test_wait_for_refresh_accepts_completed_status(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "Completed"}

    monkeypatch.setattr(refresh.requests, "get", lambda *args, **kwargs: Response())
    refresh.wait_for_refresh(
        "workspace", "dataset", "Model", "request", {"Authorization": "x"}, 1
    )
