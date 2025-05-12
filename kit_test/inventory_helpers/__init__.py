import argparse
import importlib
from importlib.util import find_spec

subcommands = [
    # "collate_tested",
    "collate_items",
    "empty_boxes",
]

helper_description = "A collection of useful inventory helpers"

if find_spec('sr.tools') is None:
    subcommands = []
    helper_description = "A collection of useful inventory helpers. Requires sr.tools"


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Subparser for the inventory subcommands."""
    parser = subparsers.add_parser(
        "inventory",
        description=helper_description,
        help=helper_description,
    )

    subparsers = parser.add_subparsers(required=True)
    for command in subcommands:
        mod_name = f"{__package__}.{command}"
        importlib.import_module(mod_name).create_subparser(subparsers)
