"""The servo board module provides an interface to the servo board firmware over serial."""
from __future__ import annotations

import atexit
import logging
from typing import NamedTuple

from .discovery import VidPid
from .serial_wrapper import SerialWrapper
from .utils import (
    BoardIdentity,
    map_to_float,
    map_to_int,
)

DUTY_MIN = 500
DUTY_MAX = 4000
START_DUTY_MIN = 1000
START_DUTY_MAX = 2000

logger = logging.getLogger(__name__)
BAUDRATE = 115200  # Since the servo board is a USB device, this is ignored
VIDPID = VidPid(0x1BDA, 0x0011)


class ServoStatus(NamedTuple):
    """A named tuple containing the values of the servo status output."""

    watchdog_failed: bool
    power_good: bool

    @classmethod
    def from_status_response(cls, response: str) -> ServoStatus:
        """
        Create a ServoStatus from a status response.

        :param response: The response from a *STATUS? command.
        :return: The ServoStatus.
        """
        data = response.split(':')

        return cls(
            watchdog_failed=(data[0] == '1'),
            power_good=(data[1] == '1'),
        )


class ServoBoard:
    """
    A class representing the servo board interface.

    This class is intended to be used to communicate with the servo board over serial
    using the text-based protocol added in version 4.3 of the servo board firmware.

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

        self.servos = tuple(
            Servo(self._serial, index) for index in range(12)
        )

        identity = self.identify()
        assert identity.board_type == 'SBv4B', \
            f"Expected board type 'SBv4B', got {identity.board_type!r} instead."

        self._serial.set_identity(identity)

        atexit.register(self._cleanup)

    def identify(self) -> BoardIdentity:
        """
        Get the identity of the board.

        :return: The identity of the board.
        """
        response = self._serial.query('*IDN?')
        return BoardIdentity(*response.split(':'))

    def status(self) -> ServoStatus:
        """
        Get the board's status.

        :return: A named tuple of the watchdog fail and pgood status.
        """
        response = self._serial.query('*STATUS?')

        return ServoStatus.from_status_response(response)

    def reset(self) -> None:
        """
        Reset the board.

        This will disable all servos.
        """
        self._serial.write('*RESET')

    def current(self) -> float:
        """
        Get the current draw of the board.

        This only includes the servos powered through the main port, not the aux port.

        :return: The current draw of the board in amps.
        """
        response = self._serial.query('SERVO:I?')
        return float(response) / 1000

    def voltage(self) -> float:
        """
        Get the voltage of the on-board regulator.

        :return: The voltage of the on-board regulator in volts.
        """
        response = self._serial.query('SERVO:V?')
        return float(response) / 1000

    def _cleanup(self) -> None:
        """
        Reset the board and disable all servos on exit.

        This is registered as an exit function.
        """
        try:
            self.reset()
        except Exception:
            logger.warning(f"Failed to cleanup servo board {self._serial}.")

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__}: {self._serial}>"


class Servo:
    """
    A class representing a servo on the servo board.

    :param serial: The serial wrapper to use to communicate with the board.
    :param index: The index of the servo on the board.
    """

    def __init__(self, serial: SerialWrapper, index: int):
        self._serial = serial
        self._index = index

        self._duty_min = START_DUTY_MIN
        self._duty_max = START_DUTY_MAX

    def get_position(self) -> float | None:
        """
        Get the position of the servo.

        If the servo is disabled, this will return None.

        :return: The position of the servo as a float between -1.0 and 1.0 or None if disabled.
        """
        response = self._serial.query(f'SERVO:{self._index}:GET?')
        data = int(response)
        if data == 0:
            return None
        return map_to_float(data, self._duty_min, self._duty_max, -1.0, 1.0, precision=3)

    def set_position(self, value: float | None) -> None:
        """
        Set the position of the servo.

        If the servo is disabled, this will enable it.
        -1.0 to 1.0 may not be the full range of the servo, see set_duty_limits().

        :param value: The position of the servo as a float between -1.0 and 1.0
            or None to disable.
        """
        if value is None:
            self.disable()
            return

        setpoint = map_to_int(value, -1.0, 1.0, self._duty_min, self._duty_max)
        self._serial.write(f'SERVO:{self._index}:SET:{setpoint}')

    def disable(self) -> None:
        """
        Disable the servo.

        This will cause this channel to output a 0% duty cycle.
        """
        self._serial.write(f'SERVO:{self._index}:DISABLE')

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__} index={self._index} {self._serial}>"
