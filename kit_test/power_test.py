
"""
Power board v4 test.

To run this with an SRv4 Power Board connect power resistors to all the 12V
outputs and the 5V output. Size the resistors so that the total current with
all 12V outputs enabled is between 10A and 25A.

The test will:
- Enable and disable the run and error LEDs
- Play the buzzer
- Detect the start button being pressed
- Test the current draw on each output with and without the output enabled
- Test the global current with multiple outputs enabled
"""
import argparse
import csv
import logging
import os
import textwrap
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Any, Dict, Optional

import serial

from .hal import BRAIN_OUTPUT, POWER_VIDPID, PowerBoard, PowerOutputPosition, discover_boards
from .hal.utils import BoardDisconnectionError

OUTPUT_RESISTANCE = [
    1.5,  # H0
    1.5,  # H1
    1.5,  # L0
    5.0,  # L1
    6.0,  # L2
    1.5,  # L3
    10.0,  # 5V
]

logger = logging.getLogger("power_test")


def log_and_assert_bounds(
    results: Dict[str, Any],
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
    results: Dict[str, Any],
    key: str,
    value: float,
    name: str,
    unit: str,
    nominal: float,
    tolerance: float,
) -> None:
    """Log a value and assert it is within bounds."""
    logger.info(f"Detected {name}: {value:.3f}{unit}")
    results[key] = value
    min = nominal * (1 - tolerance)
    max = nominal * (1 + tolerance)
    assert min < value < max, (
        f"{name.capitalize()} of {value:.3f}{unit} is outside acceptable range of "
        f"{nominal:.2f}±{tolerance:.0%}.")


def test_output(
    board: PowerBoard,
    results: Dict,
    output: PowerOutputPosition,
    input_voltage: float,
) -> None:
    """Test a single output on the power board."""
    if output == PowerOutputPosition.FIVE_VOLT:
        test_regulator(board, results)
        return

    log_and_assert_bounds(  # test off current
        results, f'out_{output.name}_off_current', board.outputs[output].current(),
        f'output {output.name} off state current', 'A', -0.2, 0.2)

    # enable output
    board.outputs[output].enable(True)
    sleep(0.5)

    expected_out_current = input_voltage / OUTPUT_RESISTANCE[output]
    log_and_assert(  # test output current
        results, f'out_{output.name}_current', board.outputs[output].current(),
        f'output {output.name} current', 'A', expected_out_current, 0.1)
    log_and_assert(  # test global current
        results, f'out_{output.name}_global_current', board.battery_sensor.current(),
        'global output current', 'A', expected_out_current, 0.1)

    # disable output
    board.outputs[output].enable(False)
    sleep(0.5)


def test_regulator(board: PowerBoard, results: Dict) -> None:
    """Test the 5V regulator on the power board."""
    # test off current
    log_and_assert_bounds(
        results, 'reg_off_current', board.outputs[PowerOutputPosition.FIVE_VOLT].current(),
        'regulator off state current', 'A', -0.2, 0.2)

    # enable output
    board.outputs[PowerOutputPosition.FIVE_VOLT].enable(True)
    sleep(0.5)

    reg_voltage = board.status().regulator_voltage
    log_and_assert_bounds(
        results, 'reg_volt', reg_voltage, 'regulator voltage', 'V', 4.5, 5.5)

    expected_reg_current = reg_voltage / OUTPUT_RESISTANCE[PowerOutputPosition.FIVE_VOLT]
    log_and_assert(
        results, 'reg_current', board.outputs[PowerOutputPosition.FIVE_VOLT].current(),
        'regulator current', 'A', expected_reg_current, 0.1)

    # disable output
    board.outputs[PowerOutputPosition.FIVE_VOLT].enable(False)
    sleep(0.5)


def test_board(
    output_writer: csv.DictWriter,
    test_uvlo: bool,
    fw_ver: Optional[str] = None,
) -> None:
    """
    Test the power board.

    The test will:
    - Enable and disable the run and error LEDs
    - Play the buzzer
    - Detect the start button being pressed
    - Test the current draw on each output with and without the output enabled
    - Test the global current with multiple outputs enabled
    """
    results: Dict[str, Any] = {}

    ports = discover_boards(POWER_VIDPID)
    if len(ports) == 0:
        logger.error("No power boards found.")
        return

    board = PowerBoard(ports[0].port, ports[0].identity)
    try:
        results['passed'] = False  # default to failure
        board_identity = board.identify()

        results['asset'] = board_identity.asset_tag
        results['sw_version'] = board_identity.sw_version
        logger.info(
            f"Running power board test on board: {board_identity.asset_tag} "
            f"running firmware version: {board_identity.sw_version}.")
        if fw_ver is not None:
            assert board_identity.sw_version == fw_ver, \
                f"Expected firmware version {fw_ver}, got {board_identity.sw_version} instead."

        board.reset()
        sleep(0.5)

        # expected currents are calculated using this voltage
        input_voltage = board.battery_sensor.voltage()
        log_and_assert_bounds(
            results, 'input_volt', input_voltage, 'input voltage', 'V', 11.5, 12.5)

        # fan
        # force the fan to run
        board.enable_fan(True)
        fan_result = input("Is the fan running? [Y/n]") or 'y'  # default to yes
        results['fan'] = fan_result
        assert fan_result.lower() == 'y', "Reported that the fan didn't work."
        board.enable_fan(False)

        # buzzer
        board.piezo.buzz(0.5, 1000)
        buzz_result = input("Did the buzzer buzz? [Y/n]") or 'y'  # default to yes
        results['buzzer'] = buzz_result
        assert buzz_result.lower() == 'y', "Reported that the buzzer didn't buzz."

        # leds
        board.run_led.flash()
        board.error_led.flash()
        led_result = input("Are the LEDs flashing? [Y/n]") or 'y'  # default to yes
        results['leds'] = led_result
        assert led_result.lower() == 'y', "Reported that the LEDs didn't work."

        board.run_led.off()
        board.error_led.off()

        # start button
        board.start_button()
        logger.info("Please press the start button")
        while not board.start_button():
            sleep(0.1)
        results['start_btn'] = "y"

        for output in PowerOutputPosition:
            test_output(board, results, output, input_voltage)

        total_expected_current = 0.0
        for output in PowerOutputPosition:
            if output == BRAIN_OUTPUT:
                continue
            total_expected_current += input_voltage / OUTPUT_RESISTANCE[output]
            if total_expected_current > 25.0:
                # stop before we hit the current limit
                break

            board.outputs[output].enable(True)
            sleep(0.5)
            log_and_assert(
                results, f'sum_out_{output.name}_current', board.battery_sensor.current(),
                f'output current up to {output.name}', 'A', total_expected_current, 0.1)
            sleep(0.5)

        # disable all outputs
        for output in PowerOutputPosition:
            board.outputs[output].enable(False)

        if test_uvlo:
            try:
                psu = serial.serial_for_url('hwgrep://0416:5011')
            except serial.SerialException:
                assert False, "Failed to connect to PSU. Is it connected?"
            psu.write(b'VSET1:11.5\n')
            # Enable output
            psu.write(b'OUT1\n')
            # start at 11.5V and drop to 10V
            for voltx10 in range(115, 100, -1):
                psu.write(f'VSET1:{voltx10 / 10}\n'.encode('ascii'))
                sleep(0.1)
                # stop when serial is lost
                try:
                    meas_voltage = board.battery_sensor.voltage()
                    logger.info(f"Measured voltage: {meas_voltage}V for {voltx10 / 10}V")
                except BoardDisconnectionError:
                    logger.info(f"Software UVLO triggered at {voltx10 / 10}V")
                    results['soft_uvlo'] = voltx10 / 10
                    break
            else:
                assert False, "Software UVLO didn't function at 10V."

            # set to 9.5V and ask if leds are off
            psu.write(b'VSET1:9.5\n')
            sleep(0.1)
            # default to yes
            hard_uvlo_result = input("Have all the LEDs turned off? [Y/n]") or 'y'
            results['hard_uvlo'] = hard_uvlo_result
            assert hard_uvlo_result.lower() == 'y', \
                "Reported that hardware UVLO didn't function."

            # set to 10.9V-11.3V and check if serial is back
            for voltx10 in range(109, 114):
                psu.write(f'VSET1:{voltx10 / 10}\n'.encode('ascii'))
                sleep(2)
                # stop when serial is back
                try:
                    meas_voltage = board.battery_sensor.voltage()
                    logger.info(f"Measured voltage: {meas_voltage}V for {voltx10 / 10}V")
                except BoardDisconnectionError:
                    pass
                else:
                    logger.info(f"Hardware UVLO cleared at {voltx10 / 10}V")
                    results['hard_uvlo_hyst'] = voltx10 / 10
                    break
            else:
                assert False, "Hardware UVLO didn't clear at 11.3V."

            # Disable output
            psu.write(b'OUT0\n')

        logger.info("Board passed")
        results['passed'] = True
    finally:
        output_writer.writerow(results)

        # Disable all outputs
        board.reset()
        board.close()


def main(args: argparse.Namespace) -> None:
    """Main function for the power board test."""
    new_log = True
    fieldnames = [
        'asset', 'sw_version', 'passed', 'input_volt',
        'reg_volt', 'reg_current', 'reg_off_current',
        'out_H0_off_current', 'out_H0_current', 'out_H0_global_current',
        'out_H1_off_current', 'out_H1_current', 'out_H1_global_current',
        'out_L0_off_current', 'out_L0_current', 'out_L0_global_current',
        'out_L1_off_current', 'out_L1_current', 'out_L1_global_current',
        'out_L2_off_current', 'out_L2_current', 'out_L2_global_current',
        'out_L3_off_current', 'out_L3_current', 'out_L3_global_current',
        'sum_out_H0_current', 'sum_out_H1_current', 'sum_out_L0_current',
        'sum_out_L1_current', 'sum_out_L2_current', 'sum_out_L3_current',
        'sum_out_FIVE_VOLT_current',
        'fan', 'leds', 'buzzer', 'start_btn',
        'soft_uvlo', 'hard_uvlo', 'hard_uvlo_hyst']

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
                test_board(writer, args.test_uvlo, args.fw_ver)
            except AssertionError as e:
                logger.error(f"Test failed: {e}")

            result = input("Test another power board? [Y/n]") or 'y'
            if result.lower() != 'y':
                break

    logger.info(f"Test results saved to {logfile}")


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """power_v4 command parser."""
    parser = subparsers.add_parser(
        "power_v4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help=(
            "Test the Power v4 board. Requires resistive loads to be connected to all outputs."
        ),
    )

    parser.add_argument('--log', default=None, help='A CSV file to save test results to.')
    parser.add_argument('--test-uvlo', action='store_true', help='Test the UVLO circuit.')
    parser.add_argument(
        '--fw-ver',
        default=None,
        help='The expected firmware version on the boards.',
    )

    parser.set_defaults(func=main)
