"""The power board module provides an interface to the power board firmware over serial."""
from __future__ import annotations

import atexit
import logging
from enum import IntEnum
from typing import NamedTuple

from .discovery import VidPid
from .serial_wrapper import SerialWrapper
from .utils import BoardIdentity

logger = logging.getLogger(__name__)
BAUDRATE = 115200  # Since the power board is a USB device, this is ignored
VIDPID = VidPid(0x1BDA, 0x0010)


class PowerOutputPosition(IntEnum):
    """
    A mapping of output name to number of the PowerBoard outputs.

    The numbers here are the same as used in communication protocol with the PowerBoard.
    """

    H0 = 0
    H1 = 1
    L0 = 2
    L1 = 3
    L2 = 4
    L3 = 5
    FIVE_VOLT = 6


class PowerStatus(NamedTuple):
    """A named tuple containing the values of the power status output."""

    overcurrent: tuple[bool, ...]
    temperature: int
    fan_running: bool
    regulator_voltage: float
    other: tuple[str, ...] = tuple()

    @classmethod
    def from_status_response(cls, response: str) -> PowerStatus:
        """
        Create a PowerStatus object from the response to a status command.

        :param response: The response from a *STATUS? command.
        :raise TypeError: If the response is invalid.
        :return: A PowerStatus object.
        """
        oc_flags, temp, fan_running, raw_voltage, *other = response.split(':')
        return cls(
            overcurrent=tuple((x == '1') for x in oc_flags.split(',')),
            temperature=int(temp),
            fan_running=(fan_running == '1'),
            regulator_voltage=float(raw_voltage) / 1000,
            other=tuple(other),
        )


# This output is always on, and cannot be controlled via the API.
BRAIN_OUTPUT = PowerOutputPosition.L2


class PowerBoard:
    """
    A class representing the power board interface.

    This class is intended to be used to communicate with the power board over serial.

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

        self.outputs = tuple(Output(self._serial, i) for i in range(7))
        self.battery_sensor = BatterySensor(self._serial)
        self.piezo = Piezo(self._serial)
        self.run_led = Led(self._serial, 'RUN')
        self.error_led = Led(self._serial, 'ERR')

        identity = self.identify()
        assert identity.board_type == 'PBv4B', \
            f"Expected board type 'PBv4B', got {identity.board_type!r} instead."
        self._serial.set_identity(identity)

        atexit.register(self._cleanup)

    def identify(self) -> BoardIdentity:
        """
        Get the identity of the board.

        :return: The identity of the board.
        """
        response = self._serial.query('*IDN?')
        return BoardIdentity(*response.split(':'))

    def status(self) -> PowerStatus:
        """
        Return the status of the power board.

        :return: The status of the power board.
        """
        response = self._serial.query('*STATUS?')
        return PowerStatus.from_status_response(response)

    def reset(self) -> None:
        """
        Reset the power board.

        This turns off all outputs except the brain output and stops any running tones.
        """
        self._serial.write('*RESET')
        # Additionally, the brain output is always on, so we need to turn it off
        # manually.
        self._serial.write('*SYS:BRAIN:SET:0')

    def start_button(self) -> bool:
        """
        Return whether the start button has been pressed.

        This value latches until the button is read, so only shows that the
        button has been pressed since this method was last called.

        :return: Whether the start button has been pressed.
        """
        response: str = self._serial.query('BTN:START:GET?')
        internal, external = response.split(':')
        return (internal == '1') or (external == '1')

    def enable_fan(self, value: bool) -> None:
        """
        Enable or disable the fan.

        :param value: Whether to enable the fan.
        """
        self._serial.write(f'*SYS:FAN:SET:{bool(value):d}')

    def _cleanup(self) -> None:
        """
        Reset the power board and turn off all outputs when exiting.

        This method is registered as an exit handler and is called to ensure
        the power board is left in a safe state.
        """
        try:
            self.reset()
        except Exception:
            logger.warning("Failed to cleanup power board.")

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__}: {self._serial}>"


class Output:
    """
    A class representing a single output of the power board.

    :param serial: The serial wrapper to use for communication.
    :param index: The index of the output to represent.
    """

    def __init__(self, serial: SerialWrapper, index: int):
        self._serial = serial
        self._index = index

    def is_enabled(self) -> bool:
        """
        Return whether the output is enabled.

        Outputs are enabled at startup, but will be disabled if the output draws
        too much current.

        :return: Whether the output is enabled.
        """
        response = self._serial.query(f'OUT:{self._index}:GET?')
        return response == '1'

    def enable(self, value: bool) -> None:
        """
        Set whether the output is enabled.

        Outputs that have been disabled due to overcurrent will not be enabled,
        but will not raise an error.

        :param value: Whether the output should be enabled.
        """
        if self._index == BRAIN_OUTPUT:
            # Changing the brain output will also raise a NACK from the firmware
            self._serial.write(f'*SYS:BRAIN:SET:{bool(value):d}')
        else:
            self._serial.write(f'OUT:{self._index}:SET:{bool(value):d}')

    def current(self) -> float:
        """
        Return the current draw of the output.

        This current measurement has a 10% tolerance.

        :return: The current draw of the output, in amps.
        """
        response = self._serial.query(f'OUT:{self._index}:I?')
        return float(response) / 1000

    def overcurrent(self) -> bool:
        """
        Return whether the output is in an overcurrent state.

        This is set when the output draws more than its maximum current.
        Resetting the power board will clear this state.

        :return: Whether the output is in an overcurrent state.
        """
        response = self._serial.query('*STATUS?')
        return PowerStatus.from_status_response(response).overcurrent[self._index]

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__} index={self._index} {self._serial}>"


class Led:
    """
    A class representing a single LED of the power board.

    :param serial: The serial wrapper to use for communication.
    :param led: The name of the LED to represent.
    """

    def __init__(self, serial: SerialWrapper, led: str):
        self._serial = serial
        self._led = led

    def on(self) -> None:
        """Turn on the LED."""
        self._serial.write(f'LED:{self._led}:SET:1')

    def off(self) -> None:
        """Turn off the LED."""
        self._serial.write(f'LED:{self._led}:SET:0')

    def flash(self) -> None:
        """Set the LED to flash at 1Hz."""
        self._serial.write(f'LED:{self._led}:SET:F')

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__} led={self._led} {self._serial}>"


class BatterySensor:
    """
    A class representing the battery sensor of the power board.

    This is implemented using an INA219 current sensor on the power board.

    :param serial: The serial wrapper to use for communication.
    """

    def __init__(self, serial: SerialWrapper):
        self._serial = serial

    def voltage(self) -> float:
        """
        Return the voltage of the battery.

        :return: The voltage of the battery, in volts.
        """
        response = self._serial.query('BATT:V?')
        return float(response) / 1000

    def current(self) -> float:
        """
        Return the current draw from the battery.

        :return: The current draw from the battery, in amps.
        """
        response = self._serial.query('BATT:I?')
        return float(response) / 1000

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__}: {self._serial}>"


class Piezo:
    """
    A class representing the piezo of the power board.

    The piezo is used to produce audible tones.

    :param serial: The serial wrapper to use for communication.
    """

    def __init__(self, serial: SerialWrapper):
        self._serial = serial

    def buzz(self, frequency: float, duration: float) -> None:
        """
        Produce a tone on the piezo.

        This method is non-blocking, and sending another tone while one is
        playing will cancel the first.

        :param frequency: The frequency of the tone, in Hz, in the range 8-10,000Hz.
        :param duration: The duration of the tone, in seconds.
        """
        frequency_int = int(frequency)
        duration_ms = int(duration * 1000)

        self._serial.write(f'NOTE:{frequency_int}:{duration_ms}')

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__}: {self._serial}>"
