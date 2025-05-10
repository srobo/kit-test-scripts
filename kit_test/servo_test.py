"""
Servo v4 board test.

To run this with an SRv4 Servo Board connect servos to all outputs.

The test will:
- Move all 12 servos
"""
import argparse
import csv
import logging
import os
import textwrap
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Any, Dict, Optional

from .hal import SERVO_VIDPID, ServoBoard, discover_boards

logger = logging.getLogger("servo_test")


def test_board(output_writer: csv.DictWriter, fw_ver: Optional[str] = None) -> None:
    """
    Test the servo board.

    This test will move all servos to the end stops and back to the middle.
    """
    results: Dict[str, Any] = {}

    ports = discover_boards(SERVO_VIDPID)
    if len(ports) == 0:
        logger.error("No servo boards found.")
        return

    board = ServoBoard(ports[0].port, ports[0].identity)
    try:
        results['passed'] = False  # default to failure
        board_identity = board.identify()

        results['asset'] = board_identity.asset_tag
        results['sw_version'] = board_identity.sw_version
        logger.info(
            f"Running servo board test on board: {board_identity.asset_tag} "
            f"running firmware version: {board_identity.sw_version}.")
        if fw_ver is not None:
            assert board_identity.sw_version == fw_ver, \
                f"Expected firmware version {fw_ver}, got {board_identity.sw_version} instead."

        board.reset()
        sleep(0.5)

        input_voltage = board.voltage()
        # expected currents are calculated using this voltage
        logger.info(f"Detected input voltage {input_voltage:.3f}V")
        results['input_volt'] = input_voltage
        assert 5 < input_voltage < 6, \
            f"Input voltage of {input_voltage:.3f}V is outside acceptable range of 5.5V±0.5V."

        # move all servos
        for i in range(12):
            board.servos[i].set_position(-0.8)
        sleep(0.5)
        for i in range(12):
            board.servos[i].set_position(0.8)
        sleep(0.5)
        for i in range(12):
            board.servos[i].set_position(-0.8)
        sleep(0.5)
        for i in range(12):
            board.servos[i].set_position(0)

        move_result = input("Did the servos move [Y/n]") or 'y'  # default to yes
        results['servos_move'] = move_result
        assert move_result.lower() == 'y', "Reported that the servos didn't move."

        logger.info("Board passed")
        results['passed'] = True
    finally:
        output_writer.writerow(results)
        board.reset()
        board.close()


def main(args: argparse.Namespace) -> None:
    """Main function for the servo board test."""
    new_log = True
    fieldnames = ['asset', 'sw_version', 'passed', 'input_volt', 'servos_move']

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
                test_board(writer, args.fw_ver)
            except AssertionError as e:
                logger.error(f"Test failed: {e}")

            result = input("Test another servo board? [Y/n]") or 'y'
            if result.lower() != 'y':
                break

    logger.info(f"Test results saved to {logfile}")


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """servo_v4 command parser."""
    parser = subparsers.add_parser(
        "servo_v4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help="Test the Servo v4 board. Requires servos to be connected to all outputs.",
    )

    parser.add_argument('--log', default=None, help='A CSV file to save test results to.')
    parser.add_argument(
        '--fw-ver',
        default=None,
        help='The expected firmware version on the boards.',
    )

    parser.set_defaults(func=main)
