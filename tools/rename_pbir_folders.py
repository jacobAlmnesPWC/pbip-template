#!/usr/bin/env python3
"""
Rename Power BI report page folders and visual folders to human-readable names

Makes PBIR code reviews actually readable by replacing GUID folder names with meaningful names:
  Pages:   50dd411cef39de30a198 → Sales_Overview_50dd411cef39de30a198
  Visuals: 2402e6f6ec7ad97e9443 → clusteredBarChart_2402e6f6ec7ad97e9443

Setup:
  1. Place this script anywhere in your repo (root, scripts/, tools/, etc.)
  2. Run from the script's directory:
       cd path/to/script
       python rename_pbir_folders.py

  Or run with full path from anywhere (example):
       python C:/MyRepo/scripts/rename_pbir_folders.py
       python scripts/rename_pbir_folders.py

2  Tip: Type "python " then drag this file into the terminal to paste its full path!

Usage:
  python rename_pbir_folders.py                                    # Auto-detect .Report folders
  python rename_pbir_folders.py /path/to/MyReport.Report          # Process specific report
  python rename_pbir_folders.py --help                             # Show help

Requirements: Python 3.7+ (no external dependencies)
"""

import json
import re
import sys
import argparse
from pathlib import Path
from typing import Optional, Tuple


def sanitize_folder_name(name: str) -> Optional[str]:
    """
    Sanitize folder names for file system compatibility

    Args:
        name: The display name to sanitize

    Returns:
        Sanitized folder name or None if name cannot be sanitized
    """
    # Replace spaces with underscores
    sanitized = re.sub(r"\s+", "_", name)

    # Remove all non-alphanumeric characters except underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "", sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    # Replace multiple consecutive underscores with single underscore
    sanitized = re.sub(r"_{2,}", "_", sanitized)

    # Handle empty names
    if not sanitized:
        return None

    return sanitized


def rename_visual_folders(page_path: Path) -> int:
    """
    Rename visual folders based on visualType and name from visual.json

    Args:
        page_path: Path to the page folder

    Returns:
        Number of visual folders successfully processed
    """
    visuals_dir = page_path / "visuals"

    # Check if visuals directory exists
    if not visuals_dir.exists():
        return 0

    # Get all visual folders
    visual_folders = [d for d in visuals_dir.iterdir() if d.is_dir()]

    if not visual_folders:
        return 0

    visual_success_count = 0

    for visual_folder in visual_folders:
        visual_json_path = visual_folder / "visual.json"

        # Check if visual.json exists
        if not visual_json_path.exists():
            print(
                f"    ⚠ Skipping visual folder '{visual_folder.name}' - no visual.json found"
            )
            continue

        try:
            # Read and parse visual.json
            with open(visual_json_path, "r", encoding="utf-8") as f:
                visual_json = json.load(f)

            # Extract visualType and name
            visual_type = visual_json.get("visual", {}).get("visualType")
            visual_name = visual_json.get("name")

            if not visual_type or not visual_name:
                print(
                    f"    ⚠ Skipping visual folder '{visual_folder.name}' - missing visualType or name"
                )
                continue

            # Create new folder name: visualType_name
            new_visual_folder_name = f"{visual_type}_{visual_name}"

            # Sanitize the folder name
            sanitized_visual_name = sanitize_folder_name(new_visual_folder_name)

            if not sanitized_visual_name:
                print(
                    f"    ⚠ Skipping visual folder '{visual_folder.name}' - name cannot be sanitized"
                )
                continue

            # Check if folder name already matches
            if visual_folder.name == sanitized_visual_name:
                print(f"    ✓ Visual already correct: {visual_folder.name}", end="")
                print(f" \033[90m(grey)\033[0m")  # Grey color  # noqa: F541
                visual_success_count += 1
                continue

            # Construct new folder path
            new_visual_folder_path = visuals_dir / sanitized_visual_name

            # Check if target folder already exists
            if new_visual_folder_path.exists():
                print(
                    f"    ⚠ Cannot rename visual '{visual_folder.name}' to '{sanitized_visual_name}' - target folder already exists"
                )
                continue

            # Rename the visual folder
            visual_folder.rename(new_visual_folder_path)
            print(
                f"    \033[92m✓ Visual renamed: {visual_folder.name} → {sanitized_visual_name}\033[0m"
            )  # Green
            visual_success_count += 1

        except Exception as e:
            print(f"    ✗ Failed to process visual folder '{visual_folder.name}': {e}")

    return visual_success_count


def rename_page_folders(report_path: Path) -> Tuple[bool, int, int]:
    """
    Rename page folders based on displayName and name from page.json

    Args:
        report_path: Path to the .Report folder

    Returns:
        Tuple of (success, pages_processed, visuals_processed)
    """
    # Construct pages directory path
    pages_dir = report_path / "definition" / "pages"

    # Verify pages directory exists
    if not pages_dir.exists():
        print(f"✗ Pages directory not found: {pages_dir}")
        return False, 0, 0

    print(f"\033[92mProcessing pages directory: {pages_dir}\033[0m")  # Green
    print()

    # Get all subdirectories (excluding pages.json)
    page_folders = [d for d in pages_dir.iterdir() if d.is_dir()]

    if not page_folders:
        print(f"⚠ No page folders found in {pages_dir}")
        return False, 0, 0

    success_count = 0
    visual_success_count = 0
    total_count = len(page_folders)

    for folder in page_folders:
        page_json_path = folder / "page.json"

        # Check if page.json exists
        if not page_json_path.exists():
            print(f"⚠ Skipping folder '{folder.name}' - no page.json found")
            continue

        try:
            # Read and parse page.json
            with open(page_json_path, "r", encoding="utf-8") as f:
                page_json = json.load(f)

            # Extract display name and name (like visuals: displayName_name)
            display_name = page_json.get("displayName")
            page_name = page_json.get("name")

            if not display_name or not page_name:
                print(
                    f"⚠ Skipping folder '{folder.name}' - missing displayName or name"
                )
                continue

            # Create new folder name: displayName_name (like visuals)
            new_page_folder_name = f"{display_name}_{page_name}"

            # Sanitize the folder name
            sanitized_name = sanitize_folder_name(new_page_folder_name)

            if not sanitized_name:
                print(f"⚠ Skipping folder '{folder.name}' - name cannot be sanitized")
                continue

            # Check if folder name already matches
            if folder.name == sanitized_name:
                print(f"\033[90m✓ Page already correct: {folder.name}\033[0m")  # Grey
                success_count += 1

                # Process visual folders within this page
                page_visual_count = rename_visual_folders(folder)
                visual_success_count += page_visual_count
                continue

            # Construct new folder path
            new_folder_path = pages_dir / sanitized_name

            # Check if target folder already exists
            if new_folder_path.exists():
                print(
                    f"⚠ Cannot rename '{folder.name}' to '{sanitized_name}' - target folder already exists"
                )
                continue

            # Rename the folder
            folder.rename(new_folder_path)
            print(
                f"\033[92m✓ Page renamed: {folder.name} → {sanitized_name}\033[0m"
            )  # Green
            success_count += 1

            # Process visual folders within the renamed page
            renamed_page_path = pages_dir / sanitized_name
            page_visual_count = rename_visual_folders(renamed_page_path)
            visual_success_count += page_visual_count

        except Exception as e:
            print(f"✗ Failed to process folder '{folder.name}': {e}")

    print()
    print("\033[96mSummary:\033[0m")  # Cyan
    print(f"  Total page folders: {total_count}")
    print(f"  \033[92mPages successfully processed: {success_count}\033[0m")  # Green
    print(
        f"  \033[93mPages failed/skipped: {total_count - success_count}\033[0m"
    )  # Yellow
    print(f"  \033[92mVisual folders processed: {visual_success_count}\033[0m")  # Green

    return (
        (success_count > 0 or visual_success_count > 0),
        success_count,
        visual_success_count,
    )


def interactive_mode() -> Optional[Path]:
    """
    Interactive mode to prompt user for report directory

    Returns:
        Path to the .Report folder or None if user wants to exit
    """
    print("\033[96m=== Power BI Page & Visual Folder Renamer ===\033[0m")
    print(
        "\033[93mThis script will rename page and visual folders to human-readable names:\033[0m"
    )
    print(
        "\033[93m  • Pages: displayName_name (e.g., Sales_Overview_50dd411cef39de30a198)\033[0m"
    )
    print(
        "\033[93m  • Visuals: visualType_name (e.g., clusteredBarChart_2402e6f6ec7ad97e9443)\033[0m"
    )
    print()
    print("\033[90mExample: /home/user/MyProject/reports/MyReport.Report\033[0m")
    print()

    while True:
        report_dir = input("Enter the full path to the .Report folder: ").strip()

        if not report_dir:
            print("\033[91mPath cannot be empty. Please try again.\033[0m")
            continue

        # Check if path ends with .Report
        if not report_dir.lower().endswith(".report"):
            print("\033[91mPath must end with '.Report'. Please try again.\033[0m")
            continue

        report_path = Path(report_dir)

        # Check if path exists
        if not report_path.exists():
            print(f"\033[91mPath does not exist: {report_path}\033[0m")
            print("\033[91mPlease check the path and try again.\033[0m")
            continue

        # Check if it's a directory
        if not report_path.is_dir():
            print(f"\033[91mPath is not a directory: {report_path}\033[0m")
            continue

        return report_path


def find_report_folders(search_root: Path, max_depth: int = 5) -> list:
    """
    Auto-detect .Report folders relative to search root

    Args:
        search_root: Directory to start searching from
        max_depth: Maximum directory depth to search

    Returns:
        List of Path objects to .Report folders found
    """
    report_folders = []

    def search_dir(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for item in path.iterdir():
                if item.is_dir():
                    if item.name.lower().endswith(".report"):
                        # Verify it's a valid PBIR report (has definition/pages)
                        if (item / "definition" / "pages").exists():
                            report_folders.append(item)
                    else:
                        search_dir(item, depth + 1)
        except PermissionError:
            pass

    search_dir(search_root, 0)
    return sorted(report_folders, key=lambda p: str(p).lower())


def auto_detect_mode(script_location: Path) -> Optional[Path]:
    """
    Auto-detect .Report folders relative to where the script is located

    Args:
        script_location: Path to this script file

    Returns:
        Path to selected .Report folder, list of paths, or None
    """
    # Search from script's parent directory (repo root if script is at root or in scripts/)
    search_root = script_location.parent

    # If script is in a subfolder like 'scripts/', search from repo root
    if search_root.name.lower() in ("scripts", "tools", "utils", "bin"):
        search_root = search_root.parent

    print("\033[96m=== Power BI Page & Visual Folder Renamer ===\033[0m")
    print(f"\033[90mSearching for .Report folders in: {search_root}\033[0m")
    print()

    report_folders = find_report_folders(search_root)

    if not report_folders:
        print("\033[93m⚠ No .Report folders found in this repository.\033[0m")
        print(
            "\033[90mTip: Place this script in a repo containing Power BI .Report folders.\033[0m"
        )
        return None

    if len(report_folders) == 1:
        # Single report found - use it automatically
        print(f"\033[92m✓ Found 1 report: {report_folders[0].name}\033[0m")
        return report_folders[0]

    # Multiple reports found - let user choose
    print(f"\033[92m✓ Found {len(report_folders)} reports:\033[0m")
    print()
    for i, folder in enumerate(report_folders, 1):
        # Show relative path from search root
        try:
            rel_path = folder.relative_to(search_root)
        except ValueError:
            rel_path = folder
        print(f"  [{i}] {rel_path}")

    print()
    print("  [0] Process ALL reports")
    print()

    while True:
        try:
            choice = input(
                "Select a report (0 for all, or 1-{0}): ".format(len(report_folders))
            ).strip()
            if not choice:
                continue
            choice_num = int(choice)
            if choice_num == 0:
                return report_folders  # Return list for batch processing
            if 1 <= choice_num <= len(report_folders):
                return report_folders[choice_num - 1]
            print("\033[91mInvalid selection. Please try again.\033[0m")
        except ValueError:
            print("\033[91mPlease enter a number.\033[0m")


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description="Rename Power BI report page and visual folders to human-readable names",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Auto-detect reports in repo
  %(prog)s /path/to/MyReport.Report          # Process specific report
  %(prog)s "C:\\MyProject\\reports\\MyReport.Report"
        """,
    )

    parser.add_argument(
        "report_directory",
        nargs="?",
        help="Path to the .Report folder (auto-detects if not specified)",
    )

    args = parser.parse_args()

    try:
        # Determine report directory
        if args.report_directory:
            report_directories = [Path(args.report_directory)]
        else:
            # Auto-detect mode - find reports relative to script location
            script_path = Path(__file__).resolve()
            result = auto_detect_mode(script_path)
            if not result:
                return 1
            # Handle single or multiple reports
            report_directories = result if isinstance(result, list) else [result]

        total_pages = 0
        total_visuals = 0

        for report_directory in report_directories:
            # Validate the provided path
            if not report_directory.exists():
                print(f"✗ Report directory does not exist: {report_directory}")
                continue

            if not str(report_directory).lower().endswith(".report"):
                print("✗ Report directory must end with '.Report'")
                continue

            # Execute the renaming
            print()
            print("\033[96mStarting page folder renaming process...\033[0m")
            print(f"Report: {report_directory}")
            print()

            success, pages_processed, visuals_processed = rename_page_folders(
                report_directory
            )
            total_pages += pages_processed
            total_visuals += visuals_processed

        if len(report_directories) > 1:
            print()
            print("\033[96m=== Overall Summary ===\033[0m")
            print(f"  Reports processed: {len(report_directories)}")
            print(f"  Total pages: {total_pages}")
            print(f"  Total visuals: {total_visuals}")

        print()
        print("\033[92mProcessing complete!\033[0m")
        return 0

    except KeyboardInterrupt:
        print()
        print("\033[93mOperation cancelled by user.\033[0m")
        return 130
    except Exception as e:
        print(f"\033[91m✗ An error occurred: {e}\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
