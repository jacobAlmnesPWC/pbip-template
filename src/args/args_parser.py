import argparse


def parse_args() -> argparse.Namespace:
    """Parse deployment CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Deploy Fabric resources using environment-specific config."
    )
    parser.add_argument(
        "--env",
        "-e",
        default="dev",
        help="Target environment (dev, test, prod).",
    )
    parser.add_argument(
        "--profile",
        "-p",
        default=None,
        help="Profile to deploy (e.g., kiwi, meny). If not specified, all discovered profiles are deployed.",
    )
    parser.add_argument(
        "--whatif",
        action="store_true",
        help="Dry-run: skip publish/unpublish steps but run all other config and parameter processing.",
    )
    parser.add_argument(
        "--git-compare-ref",
        default=None,
        help="Explicit git baseline for scoped deployment. Omit for safe full deployment.",
    )
    parser.add_argument(
        "--changed-items",
        default=None,
        help="Optional comma-separated deployable-item override.",
    )
    parser.add_argument(
        "--auth-mode",
        default=None,
        help="azure_cli, client_secret, or managed_identity. Defaults to FABRIC_CICD_AUTH_MODE.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    parse_args()
