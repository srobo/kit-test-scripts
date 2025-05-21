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
from typing import List, Optional

from sr.tools.inventory import assetcode  # type: ignore[import-untyped]
from sr.tools.inventory.inventory import get_inventory  # type: ignore[import-untyped]

logger = logging.getLogger("collate_items")
GIT_EXE = os.getenv('GIT_EXE', 'git')


def pack_box(
    box: str,
    contents: List[str],
    collation_loc: Optional[Path],
    auto_commit: bool,
) -> None:
    """Move contents into box."""
    if auto_commit:
        subprocess.check_call([GIT_EXE, 'pull', '--rebase'])

    inv = get_inventory()
    try:
        # find box, check if box contains anything
        [box_asset] = inv.query(f'code:{box}')
    except ValueError:
        raise RuntimeError(f"Box {box} not found")

    if box_asset.children:
        logger.warning(f"The box is not empty, contains {len(box_asset.children)} items.")
        empty_check = input("Continue with the transaction [Y/n]") or 'y'
        if empty_check.lower().strip() != 'y':
            return

    # Get paths on all parts to add to box
    item_paths = []
    for part in contents:
        try:
            item = inv.root.parts[assetcode.normalise(part)]
        except KeyError:
            logger.error(f"Unable to find asset {part!r}")
            continue

        if item.parent.path == box_asset.path:
            logger.warning(f"Asset {item.code} is already in box {box_asset.code}")
            continue

        item_paths.append(item.path)

    # Move parts into box
    subprocess.check_call([GIT_EXE, 'mv', *item_paths, box_asset.path])

    if collation_loc:
        collation_loc.mkdir(parents=True, exist_ok=True)

        # Move box to the target directory
        subprocess.check_call([GIT_EXE, 'mv', box_asset.path, str(collation_loc)])

    # regenerate inventory and count items now in box
    inv = get_inventory()
    [box_asset] = inv.query(f'code:{box}')
    logger.info(f"Box {box_asset.code} now contains {len(box_asset.children)} items")

    if auto_commit:
        subprocess.check_call([GIT_EXE, 'commit', '--message', f'Pack box {box}'])
        subprocess.check_call([GIT_EXE, 'pull', '--rebase'])
        subprocess.check_call([GIT_EXE, 'push'])


def main(args: argparse.Namespace) -> None:
    """Main function for collating items."""
    os.chdir(args.inventory)
    if args.base_dir:
        working_dir = args.inventory / args.base_dir
    else:
        working_dir = None

    try:
        pack_box(args.box, args.contents, working_dir, args.auto_commit)
    except RuntimeError as e:
        logger.error(e)
        exit(1)


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
        '--base_dir', '-dir', type=Path,
        help="The location to move the boxes to, relative to the base of the inventory.")
    parser.add_argument(
        '-inv', '--inventory', default=Path(os.environ.get('SR_INVENTORY', '.')), type=Path,
        help=(
            "The directory of your local checkout of the SR inventory. "
            "Uses the environment variable SR_INVENTORY for the default, "
            "currently: %(default)s"
        ))
    parser.add_argument(
        '--auto-commit', action='store_true',
        help="Automatically commit and push changes to the inventory")

    parser.set_defaults(func=main)
