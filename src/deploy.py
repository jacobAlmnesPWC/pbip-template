import sys

from args import parse_args
from helpers import (
    discover_profiles,
    deploy,
)


def main() -> None:
    # 1) Parse deployment CLI arguments
    args = parse_args()
    changed_items = (
        [item.strip() for item in args.changed_items.split(",") if item.strip()]
        if args.changed_items
        else None
    )

    # 2) Determine which explicitly enabled profiles to deploy
    if args.profile:
        profiles = [args.profile]
    else:
        profiles = discover_profiles()

    if not profiles:
        print(
            "[WARN] No enabled profiles discovered. Check config/profiles.yml."
        )
        sys.exit(1)

    print(f"\n[INFO] Profiles to deploy: {', '.join(profiles)}")
    print(f"[INFO] Environment: {args.env}")

    # 3) Deploy each enabled profile
    for profile in profiles:
        deploy(
            profile=profile,
            env=args.env,
            whatif=args.whatif,
            git_compare_ref=args.git_compare_ref,
            changed_items=changed_items,
            auth_mode=args.auth_mode,
        )


if __name__ == "__main__":
    main()
