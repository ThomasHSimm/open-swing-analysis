"""Command-line entry point for Open Swing Analysis."""

from __future__ import annotations

import argparse

from open_swing_analysis import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="open-swing",
        description="Open Swing Analysis project tools",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "status",
        help="show the current implementation status",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        print(
            "V0.1 data contracts and deterministic video ingestion are implemented; "
            "pose inference, event detection, and swing analysis are not implemented."
        )
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
