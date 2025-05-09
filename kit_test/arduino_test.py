"""
Arduino test.

To run this with an arduino, first connect the Arduino test shield to the Arduino board.
The test will:
- Detect an Arduino board by its USB VID and PID.
- Record the board's serial number.
- Optional: Record the board's asset tag.
- Flash the Arduino board with a test sketch.
- Record the test sketch's outputs.
- Flash the Arduino board with the stock firmware.
"""
import argparse
import csv
import logging
import os
import sys
import textwrap
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional

import serial

from .arduino_binaries import STOCK_FW, TEST_FW
from .arduino_flash import SUPPORTED_VID_PIDS, flash_arduino, get_avrdude_path
from .hal import discover_boards

logger = logging.getLogger("arduino_test")

BAUDRATE = 19200  # NOTE: This needs to match the baudrate in the test sketch


def parse_test_output(test_output: List[str], results: Dict[str, Any]) -> bool:
    """Parse the test output from the Arduino."""
    current_test = 1
    pass_fail = True

    lines_iter = iter(test_output)
    for line in lines_iter:
        line = line.strip()
        if not line:
            continue

        if line.startswith("TEST"):
            test_name = line.split()[1]
            try:
                test_num = int(test_name)
            except ValueError:
                continue

            assert test_num == current_test, f"Missing test {current_test}"
            current_test += 1

            if test_num == 1:
                result_line = next(lines_iter)
                results['stuck_pins'] = result_line.split()[-1] == 'OK!'
            elif test_num in range(2, 6):
                name_prefix = "" if test_num < 4 else "analog-"
                name_suffix = "sink" if test_num % 2 else "source"
                header_line = next(lines_iter)
                _volts_line = next(lines_iter)
                result_line = next(lines_iter)

                header_fields = header_line.split()
                result_fields = result_line.split()
                for pin, result_val in zip(header_fields, result_fields):
                    results[f'{name_prefix}{pin}_{name_suffix}'] = (result_val == '-OK-')
            elif test_num in range(6, 9):
                adc_level = {6: 'mid', 7: 'high', 8: 'low'}[test_num]
                adc_bounds = {6: (2.2, 2.7), 7: (3.0, 3.6), 8: (1.2, 2.0)}[test_num]
                header_line = next(lines_iter)
                volts_line = next(lines_iter)

                header_fields = header_line.split()
                result_fields = volts_line.split()
                for pin, result_val in zip(header_fields, result_fields):
                    pin_num = pin.split('-')[-1]
                    pin_result = adc_bounds[0] <= float(result_val) <= adc_bounds[1]
                    results[f'adc_{adc_level}_{pin_num}'] = pin_result
                    if not pin_result:
                        pass_fail = False

    assert current_test == 9, f"Test {current_test} not found"
    return pass_fail


def test_arduino(
    output_writer: csv.DictWriter,
    collect_asset: bool,
    avrdude: Path,
    test_sketch_hex: Path,
    stock_fw_hex: Path,
) -> None:
    """Test an arduino."""
    results: Dict[str, Any] = {}
    serial_port: Optional[serial.Serial] = None

    # Find arduino port
    ports = discover_boards(SUPPORTED_VID_PIDS)
    if len(ports) == 0:
        logger.error("No arduinos found.")
        return

    arduino = ports[0]
    serial_num = arduino.identity.asset_tag

    try:
        results['serial'] = serial_num
        results['passed'] = False  # default to failure
        if collect_asset:
            asset_tag = input("Enter the asset tag: ")
            results['asset'] = asset_tag

        # Flash arduino with test sketch
        flash_arduino(avrdude, arduino.port, test_sketch_hex)
        logger.info(f"Flashed {test_sketch_hex} to {arduino.port}")

        logger.info(f"Opening serial port {arduino.port}")
        serial_port = serial.Serial(
            port=arduino.port,
            baudrate=BAUDRATE,
            timeout=2,
        )

        try:
            *lines_bytes, test_summary_bytes = serial_port.readlines()
            lines = [line.decode('utf-8').strip() for line in lines_bytes]
            test_summary = test_summary_bytes.decode('utf-8').strip()
        except serial.SerialTimeoutException:
            logger.error("Timed out waiting for test output")
            raise AssertionError("Timed out waiting for test output")
        finally:
            serial_port.close()

        assert parse_test_output(lines, results), "Failed analog tests"
        # Test summary only contains content when there are failures
        assert test_summary == "", test_summary

        # Flash arduino with stock firmware
        flash_arduino(avrdude, arduino.port, stock_fw_hex)

        logger.info("Board passed")
        results['passed'] = True
    finally:
        output_writer.writerow(results)
        if serial_port is not None:
            serial_port.close()


def main(args: argparse.Namespace) -> None:
    """Main function for the arduino test."""
    new_log = True
    fieldnames = ['asset', 'serial', 'passed', 'stuck_pins']
    fieldnames += [f'PIN-{n}_source' for n in range(3, 13)]
    fieldnames += [f'PIN-{n}_sink' for n in range(3, 13)]
    fieldnames += [f'analog-PIN-{n}_source' for n in range(1, 6)]
    fieldnames += [f'analog-PIN-{n}_sink' for n in range(1, 6)]
    fieldnames += [
        f'adc_{lvl}_{n}'
        for lvl in ('mid', 'high', 'low')
        for n in range(0, 6)
    ]

    try:
        avrdude = get_avrdude_path()
    except FileNotFoundError:
        logger.error(
            "avrdude not found in PATH, "
            "please install the avrdude package from your package manager.")
        sys.exit(1)

    if not args.test_hex.is_file():
        logger.error(f"Test firmware not found: {args.test_hex}")
        sys.exit(1)
    if not args.stock_fw_hex.is_file():
        logger.error(f"Stock firmware not found: {args.stock_fw_hex}")
        sys.exit(1)

    if args.log:
        logfile = args.log
        if os.path.exists(logfile):
            new_log = False
    else:
        logfile = NamedTemporaryFile(delete=False).name

    with open(logfile, 'a', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if new_log:
            writer.writeheader()

        while True:
            try:
                test_arduino(
                    writer,
                    args.collect_asset,
                    avrdude,
                    args.test_hex,
                    args.stock_fw_hex,
                )
            except AssertionError as e:
                logger.error(f"Test failed: {e}")

            result = input("Test another arduino? [Y/n]") or 'y'
            if result.lower() != 'y':
                break

    logger.info(f"Test results saved to {logfile}")


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Arduino test command parser."""
    parser = subparsers.add_parser(
        "arduino",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help="Test an arduino. Requires the Arduino test shield.",
    )

    parser.add_argument('--log', default=None, help='A CSV file to save test results to.')
    parser.add_argument('--collect-asset', action='store_true',
                        help='Collect the asset tag from the Arduino board.')
    parser.add_argument(
        '--test-hex', type=Path, default=TEST_FW,
        help=(
            'The compiled hex file of the Arduino test sketch. '
            'Defaults to the packaged test firmware.'
        ))
    parser.add_argument(
        '--stock-fw-hex', type=Path, default=STOCK_FW,
        help=(
            'The compiled hex file of the Arduino firmware to leave the arduino with. '
            'Defaults to the packaged stock firmware.'
        ))

    parser.set_defaults(func=main)
