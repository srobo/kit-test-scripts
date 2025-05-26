"""Collate tested items inventory helper."""
import argparse
import csv
import io
import logging
import os
import subprocess
import textwrap
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from typing import Optional

from sr.tools.cli.inv_set_attr import replace_line  # type: ignore[import-untyped]
from sr.tools.inventory import assetcode  # type: ignore[import-untyped]
from sr.tools.inventory.inventory import (  # type: ignore[import-untyped]
    Item,
    get_inventory,
)

logger = logging.getLogger("collate_tested")
GIT_EXE = os.getenv('GIT_EXE', 'git')


def collate_tested_items(
    test_csv: Path,
    collation_loc: Optional[str],
    tested_on: date,
    include_passed: bool = False,
    include_failed: bool = False,
    validate_kch: bool = False,
) -> None:
    """Update items condition, tested_on and serial attributes."""
    inv = get_inventory()
    item: Item  # type:  ignore[no-any-unimported]
    box_asset: Item  # type:  ignore[no-any-unimported]

    try:
        # find box, check if box contains anything
        [box_asset] = inv.query(f'code:{collation_loc}')
    except ValueError:
        raise RuntimeError(f"Box {collation_loc} not found")

    data_updated = False
    with open(test_csv, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        assert reader.fieldnames is not None
        assert 'asset' in reader.fieldnames, "CSV lacks 'asset' column"
        assert 'passed' in reader.fieldnames, "CSV lacks 'passed' column"

        test_data = list(reader)

    if 'serial' in reader.fieldnames:
        for entry in test_data:
            serial = entry['serial']
            part_code = entry['asset']

            if serial and not part_code:  # find asset by serial
                # find asset by serial
                items = inv.query(f'serial:{serial}')
                if not items:
                    logger.error(f"Unable to find asset with serial number {serial!r}")
                    continue

                item = items[0]
                part_code = item.code
                data_updated = True
                # write found assetcode back into csv
                entry['asset'] = part_code

            if not serial and not part_code:
                continue

    if data_updated:
        test_csv_new = test_csv.with_stem(test_csv.stem + '_populated')
        with open(test_csv_new, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=reader.fieldnames)

            writer.writeheader()
            writer.writerows(test_data)

    asset_passed = defaultdict(bool)
    for entry in test_data:
        entry['passed'] = (entry['passed'] == 'True')
        if entry['passed']:
            asset_passed[entry['asset']] = True

    # Take the last passsing entry for each asset (or last failing if no pass)
    seen_assets = set()
    for entry in reversed(test_data):
        part_code = entry['asset']

        # Only keep the final run of each asset, note this loop iterates in reverse
        if part_code in seen_assets:
            test_data.remove(entry)
            continue

        # Make sure to keep the final successful run
        if asset_passed[part_code] and not entry['passed']:
            test_data.remove(entry)
            continue

        seen_assets.add(part_code)

    # Filter based on include_passed/include_failed
    test_data = list(filter(
        lambda x: (x['passed'] and include_passed)
        or (not x['passed'] and include_failed),
        test_data
    ))

    # Find all assets in inventory
    for entry in list(test_data):
        part_code = entry['asset']
        if not part_code:
            test_data.remove(entry)
            continue

        try:
            entry['_inv_item'] = inv.root.parts[assetcode.normalise(part_code)]
        except KeyError:
            logger.error(f"Unable to find asset {part_code!r}")
            test_data.remove(entry)
            continue

    # Check all assets are the same type
    part_types = set(entry['_inv_item'].name for entry in test_data)  # type: ignore[union-attr]
    if len(part_types) > 1:
        types = ', '.join(part_types)
        logger.warning(f"CSV contain multiple types of items: {types}")
        mix_check = input("Continue with the transaction [Y/n]") or 'y'
        if mix_check.lower().strip() != 'y':
            return

    # if asset already has serial, warn if they differ
    for entry in test_data:
        item = entry['_inv_item']
        if 'serial' not in item.info or not entry.get('serial'):
            continue

        part_code = entry['asset']
        prev_serial = item.info['serial']
        serial = entry['serial']

        if serial != prev_serial:
            logger.warning(
                f"Asset {part_code!r} previously had a recorded serial of "
                f"{prev_serial!r} updating to {serial!r}"
            )

    # TODO validate_kch
    # if validate_kch and 'kch_asset' in reader.fieldnames:
    #     for entry in test_data:
    #         item = entry['_inv_item']

    for entry in test_data:
        item = entry['_inv_item']
        logger.info(f"Processing {item.code}")
        with redirect_stdout(io.StringIO()):
            replace_line(
                item.info_path, 'condition', ('working' if entry['passed'] else 'broken'))
            replace_line(item.info_path, 'tested_on', str(tested_on))
            if entry.get('serial'):
                replace_line(item.info_path, 'serial', entry['serial'])

            subprocess.check_call([GIT_EXE, 'add', item.info_path])

    if collation_loc:
        item_paths = [
            (item := entry['_inv_item']).path  # type: ignore[union-attr]
            for entry in test_data
            if item.parent.path != box_asset.path
        ]

        if item_paths:
            # Move parts into box
            subprocess.check_call([GIT_EXE, 'mv', *item_paths, box_asset.path])


def main(args: argparse.Namespace) -> None:
    """Main function for collating tested items."""
    test_data = args.test_data.absolute()
    os.chdir(args.inventory)

    collate_tested_items(
        test_data,
        args.box,
        args.tested_on,
        args.include_passed,
        args.include_failed,
        # args.kch
    )


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Collate tested command parser."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "collate_tested",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help="Collate tested items inventory helper.",
    )
    parser.add_argument(
        '--test-data', type=Path, required=True, help="The test data CSV to process.")
    parser.add_argument('--box', help="The asset code of the box to move the items to.")
    parser.add_argument(
        '--include-passed', action='store_true',
        help="Perform updates on assets where the 'passed' column is true.")
    parser.add_argument(
        '--include-failed', action='store_true',
        help="Perform updates on assets where the 'passed' column is false.")
    # parser.add_argument(
    #     '--kch', action='store_true',
    #     help="Check values in the 'kch_asset' column match attached KCH.")
    parser.add_argument(
        '--tested-on', type=date.fromisoformat, default=date.today(),
        help="Set the date to set the tested_on attribute to. Defaults to today")
    parser.add_argument(
        '-inv', '--inventory', default=Path(os.environ.get('SR_INVENTORY', '.')), type=Path,
        help=(
            "The directory of your local checkout of the SR inventory. "
            "Uses the environment variable SR_INVENTORY for the default, "
            "currently: %(default)s"
        ))

    parser.set_defaults(func=main)
