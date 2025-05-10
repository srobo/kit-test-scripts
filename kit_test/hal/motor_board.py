"""The motor board module provides an interface to the motor board firmware over serial."""
from __future__ import annotations

import logging
from enum import IntEnum
from typing import NamedTuple

from .discovery import VidPid
from .serial_wrapper import SerialWrapper
from .utils import (
    BoardIdentity,
    map_to_float,
    map_to_int,
)

logger = logging.getLogger(__name__)
BAUDRATE = 115200
VIDPID = VidPid(0x0403, 0x6001)  # FTDI FT232R chip used on the motor board


class MotorPower(IntEnum):
    """Special values for motor power."""

    BRAKE = 0
    COAST = -1024  # A value outside the allowable range


class MotorStatus(NamedTuple):
    """A tuple representing the status of the motor board."""

    output_faults: tuple[bool, ...]
    input_voltage: float
    other: tuple[str, ...] = tuple()

    @classmethod
    def from_status_response(cls, response: str) -> MotorStatus:
        """
        Create a MotorStatus object from the response to a status command.

        :param response: The response from a *STATUS? command.
        :raise TypeError: If the response is invalid.
        :return: A MotorStatus object.
        """
        output_fault_str, input_voltage_mv, *other = response.split(':')
        output_faults = tuple((port == '1') for port in output_fault_str.split(','))
        input_voltage = float(input_voltage_mv) / 1000
        return cls(output_faults, input_voltage, tuple(other))


class MotorBoard:
    """
    A class representing the motor board interface.

    This class is intended to be used to communicate with the motor board over serial
    using the text-based protocol added in version 4.4 of the motor board firmware.

    :param serial_port: The serial port to connect to.
    :param initial_identity: The identity of the board, as reported by the USB descriptor.
    """

    def __init__(
        self,
        serial_port: str,
        initial_identity: BoardIdentity | None = None,
    ) -> None:
        if initial_identity is None:
            initial_identity = BoardIdentity()
        self._serial = SerialWrapper(serial_port, BAUDRATE, identity=initial_identity)

        self.motors = (
            Motor(self._serial, 0),
            Motor(self._serial, 1)
        )

        identity = self.identify()
        assert identity.board_type == 'MCv4B', \
            f"Expected board type 'MCv4B', got {identity.board_type!r} instead."

        self._serial.set_identity(identity)

    def identify(self) -> BoardIdentity:
        """
        Get the identity of the board.

        :return: The identity of the board.
        """
        response = self._serial.query('*IDN?')
        return BoardIdentity(*response.split(':'))

    def status(self) -> MotorStatus:
        """
        The status of the board.

        :return: The status of the board.
        """
        response = self._serial.query('*STATUS?')
        return MotorStatus.from_status_response(response)

    def reset(self) -> None:
        """
        Reset the board.

        This command disables the motors and clears all faults.
        """
        self._serial.write('*RESET')

    def close(self) -> None:
        """Close the underlying serial port."""
        self._serial.stop()

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__}: {self._serial}>"


class Motor:
    """
    A class representing a motor on the motor board.

    Each motor is controlled through the power property
    and its current can be read using the current property.

    :param serial: The serial wrapper to use to communicate with the board.
    :param index: The index of the motor on the board.
    """

    def __init__(self, serial: SerialWrapper, index: int):
        self._serial = serial
        self._index = index

    def get_power(self) -> float:
        """
        Read the current power setting of the motor.

        :return: The power of the motor as a float between -1.0 and 1.0
            or the special value MotorPower.COAST.
        """
        response = self._serial.query(f'MOT:{self._index}:GET?')

        data = response.split(':')
        enabled = (data[0] == '1')
        value = int(data[1])

        if not enabled:
            return MotorPower.COAST
        return map_to_float(value, -1000, 1000, -1.0, 1.0, precision=3)

    def set_power(self, value: float) -> None:
        """
        Set the power of the motor.

        Internally this method maps the power to an integer between
        -1000 and 1000 so only 3 digits of precision are available.

        :param value: The power of the motor as a float between -1.0 and 1.0
            or the special values MotorPower.COAST and MotorPower.BRAKE.
        """
        if value == MotorPower.COAST:
            self._serial.write(f'MOT:{self._index}:DISABLE')
            return

        setpoint = map_to_int(value, -1.0, 1.0, -1000, 1000)
        self._serial.write(f'MOT:{self._index}:SET:{setpoint}')

    def current(self) -> float:
        """
        Read the current draw of the motor.

        :return: The current draw of the motor in amps.
        """
        response = self._serial.query(f'MOT:{self._index}:I?')
        return float(response) / 1000

    def in_fault(self) -> bool:
        """
        Check if the motor is in a fault state.

        :return: True if the motor is in a fault state, False otherwise.
        """
        response = self._serial.query('*STATUS?')
        return MotorStatus.from_status_response(response).output_faults[self._index]

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__} index={self._index} {self._serial}>"
