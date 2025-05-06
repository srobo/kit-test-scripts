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
import subprocess
import sys
import textwrap
from pathlib import Path
from shutil import which
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional

import serial

from .arduino_binaries import STOCK_FW, TEST_FW
from .hal import VidPid, discover_boards

logger = logging.getLogger("arduino_test")

BAUDRATE = 19200  # NOTE: This needs to match the baudrate in the test sketch
SUPPORTED_VID_PIDS = [
    VidPid(0x2341, 0x0043),  # Arduino Uno rev 3
    VidPid(0x2A03, 0x0043),  # Arduino Uno rev 3
    VidPid(0x1A86, 0x7523),  # Uno
    VidPid(0x10C4, 0xEA60),  # Ruggeduino
    VidPid(0x16D0, 0x0613),  # Ruggeduino
]


def get_avrdude_path() -> Path:
    """Get the path to avrdude."""
    if sys.platform.startswith('win'):
        from avrdude_windows import (  # type: ignore[import-untyped,unused-ignore]
            get_avrdude_path,
        )

        return Path(get_avrdude_path())
    else:
        avrdude_path = which('avrdude')
        if avrdude_path is None:
            raise FileNotFoundError("avrdude not found in PATH")
        return Path(avrdude_path)


def flash_arduino(avrdude: Path, serial_port: str, sketch_path: Path) -> None:
    """Flash the Arduino board with a sketch binary."""
    try:
        subprocess.check_call([
            str(avrdude), "-p", "atmega328p", "-c", "arduino",
            "-P", serial_port, "-D", "-U",
            f"flash:w:{sketch_path!s}:i"
        ])
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to flash Arduino: {e}")
        raise AssertionError("Failed to flash Arduino") from e


def parse_test_output(test_output: str, results: Dict[str, Any]) -> None:
    """Parse the test output from the Arduino."""
    current_test = 1

    lines = test_output.splitlines()
    lines_iter = iter(lines)
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

            # TODO
            if test_num == 1:
                pass
            elif test_num > 1 and test_num < 6:

                pass
            elif test_num >= 6:
                pass


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

        logger.info(f"Opening serial port {arduino.port}")
        serial_port = serial.Serial(
            port=arduino.port,
            baudrate=BAUDRATE,
            timeout=30,
        )
        logger.info(f"Flashed {test_sketch_hex} to {arduino.port}")

        try:
            test_output = serial_port.read_until(b'TEST COMPLETE\n').decode('utf-8')
            test_summary = serial_port.readline().decode('utf-8').strip()
        except serial.SerialTimeoutException:
            logger.error("Timed out waiting for test output")
            raise AssertionError("Timed out waiting for test output")
        finally:
            serial_port.close()

        parse_test_output(test_output, results)
        # Test summary only contains content when there are failures
        assert test_summary == "", f"Test failed: {test_summary}"

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
    fieldnames = ['asset', 'serial', 'passed']

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
