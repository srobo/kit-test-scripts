"""
Collate items inventory helper.

A helper script for packing boxes. The boxes are moved to the base directory.
"""
import argparse
import logging
import os
import subprocess
import textwrap
from pathlib import Path
from typing import List

logger = logging.getLogger("collate_items")


def pack_box(box: str, contents: List[str]) -> None:
    """Move contents into box."""
    # move box to current folder
    subprocess.run(['sr', 'inv-mv', box], check=True)

    res = subprocess.run(
        ['sr', 'inv-findpart', box], capture_output=True, text=True)
    box_path = res.stdout.strip()

    items = []
    res = subprocess.run([
        'sr',
        'inv-query',
        f'children of code:{box}',
    ], check=True, capture_output=True, text=True)
    items = res.stdout.strip().split('\n')

    if items:
        logger.warning(f"The box is not empty, contains {len(items)} items.")
        empty_check = input("Continue with the transaction [Y/n]") or 'y'
        if empty_check.lower().strip() != 'y':
            return

    # move remaining codes to box (cd box, sr inv mv)
    os.chdir(box_path)
    subprocess.run(['sr', 'inv-mv'] + contents, check=True)
    print(len(list(Path(subprocess.run([
        'sr', 'inv-findpart', box,
    ], capture_output=True, text=True).stdout.strip()).iterdir())))


def main(args: argparse.Namespace) -> None:
    """Main function for collating items."""
    args.base_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(args.base_dir)

    pack_box(args.box, args.contents)


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Collate items command parser."""
    parser = subparsers.add_parser(
        "collate_items",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help="Collate items inventory helper.",
    )
    parser.add_argument('box', help="The box to put things in")
    parser.add_argument(
        'contents', nargs='+', help="Asset code of items to populate the box")
    parser.add_argument(
        '--base_dir', '-dir', default=Path('.'), type=Path,
        help="The directory to move the boxes to. (default: %(default)s)")

    parser.set_defaults(func=main)
