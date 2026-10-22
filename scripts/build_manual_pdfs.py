#!/usr/bin/env python3
"""Build the release-manual PDFs (user tutorial, developer manual)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_devman_pdf import CONFIG as DEVMAN_CONFIG  # noqa: E402
from build_usrman_pdf import CONFIG as USRMAN_CONFIG  # noqa: E402
from manual_pdf_builder import build_manual, check_dependencies  # noqa: E402


MANUALS = {
    "user": USRMAN_CONFIG,
    "dev": DEVMAN_CONFIG,
}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the GeLB manual PDFs for release artifacts.")
    parser.add_argument(
        "--manual",
        choices=("user", "dev", "all"),
        default="all",
        help="Manual to build: the user tutorial, the developer manual, "
             "or both (default).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    names = list(MANUALS) if args.manual == "all" else [args.manual]

    for name in names:
        config = MANUALS[name]
        print(f"\n=== {config.project_name} ===")
        dep_status = check_dependencies(config)
        if dep_status:
            return dep_status

        build_status = build_manual(config)
        if build_status:
            return build_status

    print("\nThe manual PDFs are ready in the repository root.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
