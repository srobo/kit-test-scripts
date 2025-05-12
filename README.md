# kit_test

[![Lint & build](https://github.com/srobo/kit-test-scripts/actions/workflows/test_build.yml/badge.svg)](https://github.com/srobo/kit-test-scripts/actions/workflows/test_build.yml)
[![MIT license](https://img.shields.io/badge/license-MIT-brightgreen.svg?style=flat)](https://opensource.org/licenses/MIT)

A collection of test scripts for the Student Robotics v4 kit.

## Tools

All scripts are subcommands of the kit_test entrypoint.

```bash
kit_test --help
kit_test <subcommand> [options]
```

For all the tests, adding the argument `--log <log-location>` will output all the test results to a CSV file.

### power_v4

Here we are testing all outputs can be enabled and current sense is functioning.
Additionally, we test the buzzer, LEDs and start button are functioning and finally we test both the software and hardware undervoltage protection.

To run this with an SRv4 Power Board power resistors matching the OUTPUT_RESISTANCE list in power_test.py need to be connected to each of the outputs and a power supply capable of providing 12 volts at 25 amps must be used.
For the undervoltage tests, a Tenma 72-2545 power supply controller over USB is also required.
Alongside this a changeover circuit is required to automatically switch the supply to the Tenma PSU when the output is enabled.

To run the test without the undervoltage tests, run:
```bash
kit_test power_v4
```

To run the test with the undervoltage tests, run:
```bash
kit_test power_v4 --test-uvlo
```

### motor_v4

Here we are testing the both motor outputs function and that the current sensing is functional.

To run this with an SRv4 Motor Board connect power resistors to the motor outputs.
The resistors must match the MOTOR_RESISTANCE value in motor_test.py in order for the test to function.

To run the test, run:
```bash
kit_test motor_v4
```

### servo_v4

Here we are testing that all servo outputs are functional.
Note however, that unless a separate 5 volt power supply is connected to auxiliary input, only the first 8 servos will move.

To run this with an SRv4 Servo Board connect servos to all outputs.

To run the test, run:
```bash
kit_test servo_v4
```

### arduino

Here we are testing that all the pins on the arduino are functional.

To run this test you need to attach a testing hat to the Arduino that connects all pins (except pin 13) together through resistors and biases the common point to 2.5V.

To run the test, run:
```bash
kit_test arduino
```

If you wish to program up a different firmware you can provide the argument `--stock-fw-hex` with a path pointing to the compiled hex file of the firmware you want to flash.

When testing Arduinos that the mapping of asset code to serial number is not known add `--collect-asset` to also capture the asset code.
```bash
kit_test arduino --collect-asset
```

### camera

Here we are testing that the camera is accessible and can capture undistorted images.

To run this, connect the webcam to test and point it at a test marker.
The preview will freeze and highlight the marker when it is detected in the frame.

To run the test using an 80mm marker of id 101, run:
```bash
kit_test camera --marker-id 101 --marker-size 80
```

When testing cameras that the mapping of asset code to serial number is not known add `--collect-asset` to also capture the asset code.
```bash
kit_test camera --marker-id 101 --marker-size 80 --collect-asset
```

## Inventory Helpers

