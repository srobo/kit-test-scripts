"""
Emptying boxes helper script.

This script will take a list of box asset codes and a loose location
and move all items in the boxes to the loose location.
"""
import argparse
import logging
import os
import subprocess
import textwrap
from pathlib import Path
from typing import List

from sr.tools.inventory.inventory import get_inventory  # type: ignore[import-untyped]

logger = logging.getLogger("empty_boxes")
GIT_EXE = os.getenv('GIT_EXE', 'git')


def get_boxes_contents(boxes: List[str]) -> List[str]:
    """Get a list of all the immediate children of the boxes."""
    inv = get_inventory()
    contents = inv.query(f'children of code in {{ {", ".join(boxes)} }}')
    return [item.path for item in contents]


def empty_boxes(boxes: List[str], loose: str) -> None:
    """Empty boxes to the loose location."""
    loose_path = Path(loose).resolve()
    loose_path.mkdir(parents=True, exist_ok=True)
    subprocess.run([GIT_EXE, 'mv', *get_boxes_contents(boxes), loose_path])


def main(args: argparse.Namespace) -> None:
    """Main function for emptying boxes."""
    os.chdir(args.inventory)
    empty_boxes(args.boxes, args.inventory / args.loose)


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Empty boxes command parser."""
    parser = subparsers.add_parser(
        "empty_boxes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help="Move items from boxes to a loose location.",
    )

    parser.add_argument('boxes', nargs='+', help='Box asset codes')
    parser.add_argument(
        '--loose', required=True, type=Path,
        help='Location to empty the box contents to, relative to the base of the inventory.')
    parser.add_argument(
        '-inv', '--inventory', default=Path(os.environ.get('SR_INVENTORY', '.')), type=Path,
        help=(
            "The directory of your local checkout of the SR inventory. "
            "Uses the environment variable SR_INVENTORY for the default, "
            "currently: %(default)s"
        ))

    parser.set_defaults(func=main)
