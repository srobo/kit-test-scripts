"""
Motor v4 board test.

To run this with an SRv4 Motor Board connect power resistors to the motor
outputs. Size the resistors so that the current with 100% duty cycle is
is between 2A and 8A.

The test will:
- Test the current draw on each motor in both directions at a few duty cycles
"""
import argparse
import csv
import logging
import os
import textwrap
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Any, Dict, Optional

from .hal import MOTOR_VIDPID, MotorBoard, discover_boards

MOTOR_RESISTANCE = 4.7

logger = logging.getLogger("motor_test")


def log_and_assert_bounds(
    results: dict[str, Any],
    key: str,
    value: float,
    name: str,
    unit: str,
    min: float,
    max: float,
) -> None:
    """Log a value and assert it is within bounds."""
    logger.info(f"Detected {name}: {value:.3f}{unit}")
    results[key] = value
    center = (min + max) / 2
    variance = (max - min) / 2
    assert min < value < max, (
        f"{name.capitalize()} of {value:.3f}{unit} is outside acceptable range of "
        f"{center:.2f}±{variance:.2f}{unit}.")


def log_and_assert(
    results: dict[str, Any],
    key: str,
    value: float,
    name: str,
    unit: str,
    nominal: float,
    tolerance: float,
    offset: float = 0,
) -> None:
    """Log a value and assert it is within bounds."""
    logger.info(f"Detected {name}: {value:.3f}{unit}")
    results[key] = value
    min = nominal * (1 - tolerance) - offset
    max = nominal * (1 + tolerance) + offset
    assert min < value < max, (
        f"{name.capitalize()} of {value:.3f}{unit} is outside acceptable range of "
        f"{nominal:.2f}±{tolerance:.0%}{f'±{offset:.2f}{unit}' if offset != 0 else ''}.")


def test_board(output_writer: csv.DictWriter, fw_ver: Optional[str] = None) -> None:
    """
    Test the motor board.

    This test will measure the current draw on each motor in both directions at
    a few duty cycles.
    """
    results: Dict[str, Any] = {}

    ports = discover_boards(MOTOR_VIDPID)
    if len(ports) == 0:
        logger.error("No motor boards found.")
        return

    board = MotorBoard(ports[0].port, ports[0].identity)

    try:
        results['passed'] = False  # default to failure
        board_identity = board.identify()

        results['asset'] = board_identity.asset_tag
        results['sw_version'] = board_identity.sw_version
        logger.info(
            f"Running motor board test on board: {board_identity.asset_tag} "
            f"running firmware version: {board_identity.sw_version}.")
        if fw_ver is not None:
            assert board_identity.sw_version == fw_ver, \
                f"Expected firmware version {fw_ver}, got {board_identity.sw_version} instead."

        board.reset()
        sleep(0.5)

        # expected currents are calculated using this voltage
        input_voltage = board.status().input_voltage
        log_and_assert_bounds(
            results, 'input_volt', input_voltage, 'input voltage', 'V', 11.5, 12.5)

        for motor in range(2):
            logger.info(f"Testing motor {motor}")
            # test off current
            log_and_assert_bounds(
                results, f'motor_{motor}_off_current', board.motors[motor].current(),
                f'motor {motor} off state current', 'A', -0.2, 0.2)

            for direction in (1, -1):
                for abs_power in range(100, 10, -20):
                    power = abs_power * direction
                    logger.info(f"Testing {power:.0f}% power")
                    board.motors[motor].set_power(power / 100)
                    sleep(0.1)

                    expected_out_current = (
                        (input_voltage / MOTOR_RESISTANCE) * (abs_power / 100))
                    # test output current
                    log_and_assert(
                        results, f'motor_{motor}_{power}_current',
                        board.motors[motor].current(),
                        f"motor {motor}, {power:.0f}% power", 'A',
                        expected_out_current,
                        0.1, 0.2)

        logger.info("Board passed")
        results['passed'] = True
    finally:
        output_writer.writerow(results)
        board.reset()


def main(args: argparse.Namespace) -> None:
    """Main function for the motor board test."""
    new_log = True
    fieldnames = [
        'asset', 'sw_version', 'passed', 'input_volt',
        'motor_0_off_current', 'motor_1_off_current',
    ] + [
        f'motor_{motor}_{power * direction:.0f}_current'
        for motor in range(2)
        for direction in (1, -1)
        for power in range(100, 10, -20)
    ]

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

            result = input("Test another motor board? [Y/n]") or 'y'
            if result.lower() != 'y':
                break

    logger.info(f"Test results saved to {logfile}")


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """motor_v4 command parser."""
    parser = subparsers.add_parser(
        "motor_v4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help=(
            "Test the Motor v4 board. Requires resistive loads to be connected to all outputs."
        ),
    )

    parser.add_argument('--log', default=None, help='A CSV file to save test results to.')
    parser.add_argument(
        '--fw-ver',
        default=None,
        help='The expected firmware version on the boards.',
    )

    parser.set_defaults(func=main)
