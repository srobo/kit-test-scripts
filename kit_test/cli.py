"""The kit_test CLI."""
from __future__ import annotations

import argparse
import importlib
import logging
import warnings
from typing import Sequence

from ._version import version

subcommands = [
    "power_test",
    "motor_test",
    "servo_test",
    "arduino_test",
    "arduino_flash",
    "camera_test",
    "inventory_helpers",
]


def build_argparser() -> argparse.ArgumentParser:
    """Load subparsers from available subcommands."""
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(required=True)
    for command in subcommands:
        try:
            mod_name = f"{__package__}.{command}"
            importlib.import_module(mod_name).create_subparser(subparsers)
        except ImportError:
            warnings.warn(
                f"Failed to import dependencies of {mod_name} subcommand, skipping it. "
                f"Install the cli dependencies to enable it.")

    parser.add_argument(
        '--version', action='version', version=version, help="Print package version")
    parser.add_argument('--debug', action='store_true', help="Enable debug logging")

    return parser


def setup_logger(debug: bool = False) -> None:
    """Output all loggers to console with custom format at level INFO or DEBUG."""
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # log from all loggers to stdout
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    if debug:
        root_logger.setLevel(logging.DEBUG)


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry-point."""
    parser = build_argparser()
    args = parser.parse_args(argv)
    setup_logger(debug=args.debug)

    if "func" in args:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
