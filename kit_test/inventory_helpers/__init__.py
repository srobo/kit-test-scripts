import argparse
import importlib

subcommands = [
    # "collate_tested",
    "collate_items",
    "empty_boxes",
]


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Subparser for the inventory subcommands."""
    parser = subparsers.add_parser(
        "inventory",
        description="A collection of useful inventory helpers",
        help="A collection of useful inventory helpers",
    )

    subparsers = parser.add_subparsers(required=True)
    for command in subcommands:
        mod_name = f"{__package__}.{command}"
        importlib.import_module(mod_name).create_subparser(subparsers)
