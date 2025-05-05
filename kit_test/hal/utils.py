"""General utility functions and classes for the sbot package."""
from __future__ import annotations

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Add a TRACE level to logging, below DEBUG
TRACE = 5


class BoardIdentity(NamedTuple):
    """
    A container for the identity of a board.

    All the board firmwares should return this information in response to
    the *IDN? query.

    :param manufacturer: The manufacturer of the board
    :param board_type: The short name of the board, i.e. PBv4B
    :param asset_tag: The asset tag of the board,
        this should match what is printed on the board
    :param sw_version: The firmware version of the board
    """

    manufacturer: str = ""
    board_type: str = ""
    asset_tag: str = ""
    sw_version: str = ""


def map_to_int(
        x: float,
        in_min: float,
        in_max: float,
        out_min: int,
        out_max: int,
) -> int:
    """
    Map a value from the input range to the output range, returning the value as an int.

    This is used to convert a float value to an integer value for sending to the board.

    :param x: The value to map
    :param in_min: The lower bound of the input range
    :param in_max: The upper bound of the input range
    :param out_min: The lower bound of the output range
    :param out_max: The upper bound of the output range
    :return: The mapped value
    """
    value = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    return int(value)


def map_to_float(
        x: int,
        in_min: int,
        in_max: int,
        out_min: float,
        out_max: float,
        precision: int = 3,
) -> float:
    """
    Map a value from the input range to the output range, returning the value as a float.

    This is used to convert an integer value from the board to a float value.

    :param x: The value to map
    :param in_min: The lower bound of the input range
    :param in_max: The upper bound of the input range
    :param out_min: The lower bound of the output range
    :param out_max: The upper bound of the output range
    :param precision: The number of decimal places to round the output to, defaults to 3
    :return: The mapped value
    """
    value = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    return round(value, precision)


class BoardDisconnectionError(IOError):
    """Raised when communication to a board fails and cannot be reestablished."""

    pass
