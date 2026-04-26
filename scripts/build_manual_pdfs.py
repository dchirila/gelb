#!/usr/bin/env python3
"""Build the release-manual PDF (the user tutorial) from the Sphinx sources."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_usrman_pdf import CONFIG as USRMAN_CONFIG  # noqa: E402
from manual_pdf_builder import build_manual, check_dependencies  # noqa: E402


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the GeLB manual PDF for release artifacts.")
    parser.add_argument(
        "--manual",
        choices=("user",),
        default="user",
        help="Manual to build (only the user tutorial).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _parse_args(argv)
    config = USRMAN_CONFIG

    print(f"\n=== {config.project_name} ===")
    dep_status = check_dependencies(config)
    if dep_status:
        return dep_status

    build_status = build_manual(config)
    if build_status:
        return build_status

    print("\nThe manual PDF is ready in the repository root.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
