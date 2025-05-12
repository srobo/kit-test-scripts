"""
Emptying boxes helper script.

This script will take a list of box asset codes and a loose location
and move all items in the boxes to the loose location.
"""
import argparse
import logging
import subprocess
import textwrap
from pathlib import Path
from typing import List

logger = logging.getLogger("empty_boxes")


def get_boxes_contents(boxes: List[str]) -> List[str]:
    """Get a list of all the immediate children of the boxes."""
    res = subprocess.run([
        'sr',
        'inv-query',
        f'children of code in {{ {", ".join(boxes)} }}',
    ], check=True, capture_output=True, text=True)
    return res.stdout.strip().split('\n')


def empty_boxes(boxes: List[str], loose: str) -> None:
    """Empty boxes to the loose location."""
    loose_path = Path(loose).resolve()
    loose_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'mv', *get_boxes_contents(boxes), loose_path])


def main(args: argparse.Namespace) -> None:
    """Main function for emptying boxes."""
    empty_boxes(args.boxes, args.loose)


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
        '--loose', default='.',
        help='Location to empty the box contents to. (default: %(default)s)')

    parser.set_defaults(func=main)
