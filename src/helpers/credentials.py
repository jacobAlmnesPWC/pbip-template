"""Explicit credential selection for local and CI execution."""

import os

from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
)

SUPPORTED_AUTH_MODES = {"azure_cli", "client_secret", "managed_identity"}


def get_token_credential(auth_mode: str | None = None) -> TokenCredential:
    """Return the configured credential without ever reading secrets from files."""
    mode = (
        (auth_mode or os.getenv("FABRIC_CICD_AUTH_MODE", "azure_cli")).strip().lower()
    )
    if mode not in SUPPORTED_AUTH_MODES:
        raise ValueError(
            f"Unsupported auth mode '{mode}'. Choose one of: "
            f"{', '.join(sorted(SUPPORTED_AUTH_MODES))}."
        )
    if mode == "azure_cli":
        return AzureCliCredential()
    if mode == "managed_identity":
        return ManagedIdentityCredential()

    required = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError(
            "client_secret authentication requires these environment variables: "
            + ", ".join(missing)
        )
    return ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
