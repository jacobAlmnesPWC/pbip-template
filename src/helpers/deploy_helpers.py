"""Profile-aware, conservative Fabric item deployment helpers."""

import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml
from fabric_cicd import deploy_with_config, get_changed_items

from .credentials import get_token_credential

root_directory = Path(__file__).resolve().parent.parent.parent
config_directory = root_directory / "config"
profiles_path = config_directory / "profiles.yml"
INITIAL_CATALOG_PATTERN = re.compile(
    r'initial catalog\s*=\s*"?(?P<name>[^";]+)"?', re.IGNORECASE
)


@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    config_path: Path
    refresh_mode: str


@dataclass(frozen=True)
class ProfilePaths:
    profile: str
    config_path: Path
    parameter_path: Path | None
    repository_directory: Path


@dataclass(frozen=True)
class DeploymentScope:
    should_deploy: bool
    full_deploy: bool
    changed_items: list[str] | None
    reason: str


def load_profile_definitions() -> dict[str, ProfileDefinition]:
    """Load and validate the explicit profile manifest."""
    if not profiles_path.exists():
        raise ValueError(f"Profile manifest not found: {profiles_path}")
    content = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
    entries = content.get("profiles")
    if not isinstance(entries, list) or not entries:
        raise ValueError("config/profiles.yml must contain a non-empty profiles list.")

    definitions: dict[str, ProfileDefinition] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each profile entry must be a YAML object.")
        name = str(entry.get("name", "")).strip()
        config_name = str(entry.get("config", "")).strip()
        enabled = entry.get("enabled", True)
        refresh_mode = str(entry.get("refresh", "none")).strip().lower()
        if not name or not config_name:
            raise ValueError("Each profile must define both name and config.")
        if not isinstance(enabled, bool):
            raise ValueError(f"Profile '{name}' has non-boolean enabled value.")
        if refresh_mode not in {"none", "trigger", "wait"}:
            raise ValueError(
                f"Profile '{name}' has invalid refresh mode '{refresh_mode}'."
            )
        if not enabled:
            continue
        if name in definitions:
            raise ValueError(f"Profile '{name}' is listed more than once.")
        config_path = (config_directory / config_name).resolve()
        if config_path.parent != config_directory.resolve():
            raise ValueError(f"Profile '{name}' config must remain inside config/.")
        definitions[name] = ProfileDefinition(name, config_path, refresh_mode)
    return definitions


def discover_profiles() -> list[str]:
    return sorted(load_profile_definitions())


def get_profile_definition(profile: str) -> ProfileDefinition:
    definitions = load_profile_definitions()
    try:
        return definitions[profile]
    except KeyError as error:
        raise ValueError(f"Unknown or disabled profile '{profile}'.") from error


def get_config_path(profile: str) -> Path:
    return get_profile_definition(profile).config_path


def get_profile_paths(profile: str) -> ProfilePaths:
    config_path = get_config_path(profile)
    if not config_path.exists():
        raise ValueError(
            f"Config for profile '{profile}' does not exist: {config_path}"
        )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    core = config.get("core", {})
    repository_setting = core.get("repository_directory")
    if not repository_setting:
        raise ValueError(
            f"Config for profile '{profile}' is missing core.repository_directory."
        )
    parameter_setting = core.get("parameter")
    parameter_path = (
        (config_path.parent / parameter_setting).resolve()
        if parameter_setting
        else None
    )
    return ProfilePaths(
        profile=profile,
        config_path=config_path.resolve(),
        parameter_path=parameter_path,
        repository_directory=(config_path.parent / repository_setting).resolve(),
    )


def get_profile_config(profile: str) -> dict:
    return yaml.safe_load(get_config_path(profile).read_text(encoding="utf-8")) or {}


def get_workspace_id(profile: str, env: str) -> str:
    workspace_id = str(
        get_profile_config(profile).get("core", {}).get("workspace_id", {}).get(env, "")
    ).strip()
    if not workspace_id or workspace_id.startswith("00000000-"):
        raise ValueError(
            f"Profile '{profile}' is missing a real core.workspace_id.{env}."
        )
    return workspace_id


def normalize_items(items: Iterable[str]) -> list[str]:
    return sorted({item.strip() for item in items if item and item.strip()})


def to_root_relative(path: Path) -> str:
    return path.resolve().relative_to(root_directory.resolve()).as_posix()


def get_changed_paths(git_compare_ref: str, paths: Iterable[Path]) -> list[str]:
    relative_paths = [to_root_relative(path) for path in paths]
    if not relative_paths:
        return []
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            f"{git_compare_ref}..HEAD",
            "--",
            *relative_paths,
        ],
        cwd=root_directory,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Failed to evaluate git diff for deployment scope: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return [
        line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line
    ]


def iter_item_directories(repository_directory: Path, suffix: str) -> list[Path]:
    return sorted(
        [path for path in repository_directory.rglob(f"*{suffix}") if path.is_dir()],
        key=lambda path: path.as_posix(),
    )


def get_item_display_name(item_directory: Path) -> str:
    platform_path = item_directory / ".platform"
    if platform_path.exists():
        try:
            display_name = (
                json.loads(platform_path.read_text(encoding="utf-8"))
                .get("metadata", {})
                .get("displayName", "")
                .strip()
            )
        except json.JSONDecodeError:
            display_name = ""
        if display_name:
            return display_name
    return item_directory.name.removesuffix(".SemanticModel").removesuffix(".Report")


def find_item_directory(repository_directory: Path, item_name: str) -> Path | None:
    return next(
        (path for path in repository_directory.rglob(item_name) if path.is_dir()), None
    )


def list_profile_semantic_models(repository_directory: Path) -> list[str]:
    return sorted(
        path.name
        for path in iter_item_directories(repository_directory, ".SemanticModel")
    )


def build_semantic_model_lookup(repository_directory: Path) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for model_directory in iter_item_directories(
        repository_directory, ".SemanticModel"
    ):
        item_name = model_directory.name
        for value in (
            item_name,
            item_name.removesuffix(".SemanticModel"),
            get_item_display_name(model_directory),
        ):
            lookup[value.casefold()] = item_name
    return lookup


def resolve_report_semantic_model(
    report_directory: Path, semantic_model_lookup: dict[str, str]
) -> str | None:
    definition_path = report_directory / "definition.pbir"
    if not definition_path.exists():
        return None
    try:
        dataset_reference = json.loads(definition_path.read_text(encoding="utf-8")).get(
            "datasetReference", {}
        )
    except json.JSONDecodeError:
        return None
    model_path = dataset_reference.get("byPath", {}).get("path")
    if model_path:
        model_name = (definition_path.parent / model_path).resolve().name
        if model_name.endswith(".SemanticModel"):
            return semantic_model_lookup.get(model_name.casefold(), model_name)
    connection_string = str(
        dataset_reference.get("byConnection", {}).get("connectionString", "")
    )
    match = INITIAL_CATALOG_PATTERN.search(connection_string)
    return (
        semantic_model_lookup.get(match.group("name").strip().casefold())
        if match
        else None
    )


def expand_changed_items(
    repository_directory: Path, changed_items: Iterable[str]
) -> tuple[list[str], str]:
    changed = normalize_items(changed_items)
    if not changed:
        return [], "No changed deployable items detected for profile."
    changed_models = [item for item in changed if item.endswith(".SemanticModel")]
    if not changed_models:
        return changed, "Detected changed deployable items via git diff."

    lookup = build_semantic_model_lookup(repository_directory)
    model_to_reports: dict[str, set[str]] = defaultdict(set)
    unresolved_reports: list[str] = []
    for report in iter_item_directories(repository_directory, ".Report"):
        model = resolve_report_semantic_model(report, lookup)
        if model:
            model_to_reports[model].add(report.name)
        else:
            unresolved_reports.append(report.name)
    dependent_reports = set(unresolved_reports)
    for model in changed_models:
        dependent_reports.update(model_to_reports.get(model, set()))
    expanded = normalize_items([*changed, *dependent_reports])
    reason = "Semantic model change detected; expanded scope to dependent reports"
    if unresolved_reports:
        reason += " and unresolved report bindings as a safety fallback."
    else:
        reason += "."
    return expanded, reason


def resolve_deployment_scope(
    profile: str,
    git_compare_ref: str | None = None,
    changed_items: list[str] | None = None,
) -> DeploymentScope:
    paths = get_profile_paths(profile)
    if changed_items is not None:
        effective_items, reason = expand_changed_items(
            paths.repository_directory, changed_items
        )
        return DeploymentScope(
            should_deploy=bool(effective_items),
            full_deploy=False,
            changed_items=effective_items,
            reason=f"Manual changed-items override provided. {reason}",
        )
    if not git_compare_ref:
        return DeploymentScope(
            True, True, None, "No explicit baseline; using safe full profile deploy."
        )

    support_paths = [paths.config_path]
    if paths.parameter_path:
        support_paths.append(paths.parameter_path)
    support_paths.append(profiles_path)
    changed_support_files = get_changed_paths(git_compare_ref, support_paths)
    if changed_support_files:
        return DeploymentScope(
            True,
            True,
            None,
            "Config or parameter file changed for profile: "
            + ", ".join(changed_support_files),
        )
    effective_items, reason = expand_changed_items(
        paths.repository_directory,
        get_changed_items(paths.repository_directory, git_compare_ref=git_compare_ref),
    )
    return DeploymentScope(bool(effective_items), False, effective_items, reason)


def get_semantic_models_to_refresh(profile: str, scope: DeploymentScope) -> list[str]:
    if not scope.should_deploy:
        return []
    if scope.full_deploy:
        return list_profile_semantic_models(
            get_profile_paths(profile).repository_directory
        )
    return [
        item for item in scope.changed_items or [] if item.endswith(".SemanticModel")
    ]


def deploy(
    profile: str,
    env: str,
    whatif: bool = False,
    git_compare_ref: str | None = None,
    changed_items: list[str] | None = None,
    auth_mode: str | None = None,
) -> None:
    # Validate the target before fabric-cicd starts making API calls.
    get_workspace_id(profile, env)
    scope = resolve_deployment_scope(profile, git_compare_ref, changed_items)
    print(f"[INFO] {profile}: {scope.reason}")
    if not scope.should_deploy:
        print(f"[INFO] {profile}: no deployable changes; skipping.")
        return
    config_override: dict = {}
    if whatif:
        config_override["publish"] = {"skip": {env: True}}
        config_override["unpublish"] = {"skip": {env: True}}
    if not scope.full_deploy:
        config_override.setdefault("publish", {})["items_to_include"] = (
            scope.changed_items
        )
    deploy_with_config(
        config_file_path=str(get_config_path(profile)),
        environment=env,
        config_override=config_override or None,
        token_credential=get_token_credential(auth_mode),
    )
    mode = "full" if scope.full_deploy else "scoped"
    print(f"[SUCCESS] {profile}: deployed to {env} ({mode}).")
