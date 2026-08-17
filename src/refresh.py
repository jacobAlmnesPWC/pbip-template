"""Optional post-deploy Power BI semantic-model refreshes."""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from helpers import (
    discover_profiles,
    get_profile_definition,
    get_profile_paths,
    get_semantic_models_to_refresh,
    get_workspace_id,
    resolve_deployment_scope,
)
from helpers.credentials import get_token_credential
from helpers.deploy_helpers import find_item_directory, get_item_display_name

POWERBI_API = "https://api.powerbi.com/v1.0/myorg"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


def get_headers(auth_mode: str | None) -> dict[str, str]:
    token = get_token_credential(auth_mode).get_token(POWERBI_SCOPE).token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_dataset_id(
    workspace_id: str, model_name: str, headers: dict[str, str]
) -> str | None:
    response = requests.get(
        f"{POWERBI_API}/groups/{workspace_id}/datasets", headers=headers, timeout=30
    )
    response.raise_for_status()
    return next(
        (
            dataset["id"]
            for dataset in response.json().get("value", [])
            if dataset.get("name") == model_name
        ),
        None,
    )


def trigger_refresh(
    workspace_id: str,
    dataset_id: str,
    model_name: str,
    headers: dict[str, str],
    full: bool = False,
) -> str | None:
    payload: dict[str, object] = {"notifyOption": "NoNotification"}
    if full:
        payload = {
            "type": "Full",
            "commitMode": "Transactional",
            "applyRefreshPolicy": False,
            "retryCount": 1,
        }
    response = requests.post(
        f"{POWERBI_API}/groups/{workspace_id}/datasets/{dataset_id}/refreshes",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if response.status_code == 400:
        try:
            error_code = response.json().get("error", {}).get("code")
        except ValueError:
            error_code = None
        if error_code == "RefreshInProgressException":
            print(f"[WARN] {model_name}: refresh already in progress.")
            return None
    if response.status_code not in (200, 202):
        raise RuntimeError(
            f"{model_name}: refresh request failed (HTTP {response.status_code}): "
            f"{response.text or response.reason}"
        )
    request_id = response.headers.get("x-ms-request-id")
    if not request_id:
        request_id = response.headers.get("Location", "").rstrip("/").split("/")[-1]
    print(f"[SUCCESS] {model_name}: refresh started (HTTP {response.status_code}).")
    return request_id or None


def wait_for_refresh(
    workspace_id: str,
    dataset_id: str,
    model_name: str,
    request_id: str,
    headers: dict[str, str],
    timeout_seconds: int,
) -> None:
    """Poll the documented execution-details endpoint until terminal status."""
    deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
    url = f"{POWERBI_API}/groups/{workspace_id}/datasets/{dataset_id}/refreshes/{request_id}"
    while datetime.now(timezone.utc) < deadline:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 202:
            time.sleep(15)
            continue
        response.raise_for_status()
        result = response.json()
        status = result.get("status")
        if status == "Completed":
            print(f"[SUCCESS] {model_name}: refresh completed.")
            return
        details = result.get("serviceExceptionJson") or result.get("messages") or result
        raise RuntimeError(
            f"{model_name}: refresh ended with status {status}: {details}"
        )
    raise TimeoutError(
        f"{model_name}: refresh did not complete within {timeout_seconds}s."
    )


def refresh_profile(
    profile: str,
    env: str,
    headers: dict[str, str],
    mode: str,
    git_compare_ref: str | None = None,
    changed_items: list[str] | None = None,
    semantic_model: str | None = None,
    full: bool = False,
    timeout_seconds: int = 3600,
) -> list[str]:
    if mode == "none":
        print(f"[INFO] {profile}: refresh policy is none; skipping.")
        return []
    if semantic_model:
        models = [semantic_model]
    else:
        scope = resolve_deployment_scope(profile, git_compare_ref, changed_items)
        print(f"[INFO] {profile}: {scope.reason}")
        models = get_semantic_models_to_refresh(profile, scope)
    if not models:
        print(f"[INFO] {profile}: no semantic models require refresh.")
        return []

    workspace_id = get_workspace_id(profile, env)
    repository_directory = get_profile_paths(profile).repository_directory
    failed: list[str] = []
    for model_item_name in models:
        model_directory = find_item_directory(repository_directory, model_item_name)
        model_name = (
            get_item_display_name(model_directory)
            if model_directory is not None
            else model_item_name.removesuffix(".SemanticModel")
        )
        dataset_id = get_dataset_id(workspace_id, model_name, headers)
        if not dataset_id:
            failed.append(f"{profile}:{model_name} (dataset not found)")
            continue
        try:
            request_id = trigger_refresh(
                workspace_id, dataset_id, model_name, headers, full=full
            )
            if mode == "wait" and request_id:
                wait_for_refresh(
                    workspace_id,
                    dataset_id,
                    model_name,
                    request_id,
                    headers,
                    timeout_seconds,
                )
            elif mode == "wait":
                raise RuntimeError(
                    f"{model_name}: cannot confirm completion without a refresh request ID."
                )
        except (requests.RequestException, RuntimeError, TimeoutError) as error:
            failed.append(f"{profile}:{model_name} ({error})")
    return failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh deployed Power BI semantic models."
    )
    parser.add_argument("--env", "-e", required=True)
    parser.add_argument("--profile", "-p", default=None)
    parser.add_argument("--git-compare-ref", default=None)
    parser.add_argument("--changed-items", default=None)
    parser.add_argument("--auth-mode", default=None)
    parser.add_argument("--mode", choices=("none", "trigger", "wait"), default=None)
    parser.add_argument("--semantic-model", default=None)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.semantic_model and not args.full:
        raise ValueError("--semantic-model is a manual enhanced refresh; pass --full.")
    changed_items = (
        [item.strip() for item in args.changed_items.split(",") if item.strip()]
        if args.changed_items
        else None
    )
    profiles = [args.profile] if args.profile else discover_profiles()
    headers = get_headers(args.auth_mode)
    failed: list[str] = []
    for profile in profiles:
        configured_mode = get_profile_definition(profile).refresh_mode
        failed.extend(
            refresh_profile(
                profile=profile,
                env=args.env,
                headers=headers,
                mode=args.mode or configured_mode,
                git_compare_ref=args.git_compare_ref,
                changed_items=changed_items,
                semantic_model=args.semantic_model,
                full=args.full,
                timeout_seconds=args.timeout_seconds,
            )
        )
    if failed:
        raise RuntimeError("Refresh failed: " + "; ".join(failed))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[ERROR] {error}")
        sys.exit(1)
