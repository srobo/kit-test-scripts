"""Board discovery helper methods."""
from __future__ import annotations

import logging
from typing import NamedTuple

from serial.tools.list_ports import comports
from serial.tools.list_ports_common import ListPortInfo

from .utils import BoardIdentity

logger = logging.getLogger(__name__)


class VidPid(NamedTuple):
    """A named tuple containing the vendor ID and product ID of a USB device."""

    vendor_id: int
    product_id: int

    def __str__(self) -> str:
        return f"{self.vendor_id:04X}:{self.product_id:04X}"


class Port(NamedTuple):
    """A named tuple containing the port name and USB identity."""

    port: str
    identity: BoardIdentity

    def __str__(self) -> str:
        return f"{self.port} ({self.identity})"


def discover_boards(pidvids: list[VidPid] | VidPid) -> list[Port]:
    """
    Discover boards connected to the system.

    :param pidvids: A list of vendor ID and product ID pairs to search for.
        If a single pair is given, it will be used as a filter.
    :return: A list of ports for the discovered boards.
    """
    if isinstance(pidvids, VidPid):
        pidvids = [pidvids]

    boards: list[Port] = []

    for port in comports():
        if port.vid is None or port.pid is None:
            # Skip ports that don't have a VID or PID
            continue

        vidpid = VidPid(port.vid, port.pid)
        # Filter to USB vendor and product ID values provided
        if vidpid not in pidvids:
            continue

        # Create board identity from USB port info
        initial_identity = get_USB_identity(port)

        boards.append(
            Port(port.device, initial_identity)
        )

    return boards


def get_USB_identity(port: ListPortInfo) -> BoardIdentity:
    """
    Generate an approximate identity for a board using the USB descriptor.

    This data will be overridden by the firmware once communication is established,
    but is used for early logging messages and error handling.

    :param port: The USB port information from pyserial
    :return: An initial identity for the board
    """
    try:
        return BoardIdentity(
            manufacturer=port.manufacturer or "",
            board_type=port.product or "",
            asset_tag=port.serial_number or "",
        )
    except Exception:
        logger.warning(
            f"Failed to pull identifying information from serial device {port.device}")
        return BoardIdentity()
