"""
Arduino programming helper.

This will:
- Detect an Arduino board by its USB VID and PID.
- Flash the Arduino board with the provided firmware.
"""
import argparse
import logging
import subprocess
import sys
import textwrap
from pathlib import Path
from shutil import which

from .arduino_binaries import STOCK_FW
from .hal import VidPid, discover_boards

logger = logging.getLogger("arduino_flasher")

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

    logger.info(f"Flashed {sketch_path} to {serial_port}")


def main(args: argparse.Namespace) -> None:
    """Main function for flashing arduinos."""
    try:
        avrdude = get_avrdude_path()
    except FileNotFoundError:
        logger.error(
            "avrdude not found in PATH, "
            "please install the avrdude package from your package manager.")
        sys.exit(1)

    if not args.fw_hex.is_file():
        logger.error(f"Firmware not found: {args.fw_hex}")
        sys.exit(1)

    while True:
        try:
            # Find arduino port
            ports = discover_boards(SUPPORTED_VID_PIDS)
            assert len(ports) > 0, "No arduinos found."

            # Use the first arduino found
            arduino = ports[0]

            # Flash arduino with sketch
            flash_arduino(avrdude, arduino.port, args.fw_hex)
        except AssertionError as e:
            logger.error(f"Flashing failed: {e}")

        result = input("Flash another arduino? [Y/n]") or 'y'
        if result.lower() != 'y':
            break


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Arduino test command parser."""
    parser = subparsers.add_parser(
        "flash_arduino",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help="Flash an Arduino with a pre-compiled sketch.",
    )

    parser.add_argument(
        '-f', '--fw-hex', type=Path, default=STOCK_FW,
        help=(
            'The compiled hex file of the Arduino firmware to flash the arduino with. '
            'Defaults to the packaged stock firmware.'
        ))

    parser.set_defaults(func=main)
