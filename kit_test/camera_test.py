"""
Camera board test.

To run this with a camera, first print the AprilTag marker and place it in front of the camera.

The test will:
- Detect a camera by it's USB VID and PID.
- Records the camera's serial number.
- Optional: Record the camera's asset tag.
- Detect a printed AprilTag marker.
- Record the marker's distance from the camera.
"""
import argparse
import csv
import logging
import os
import textwrap
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional

import cv2
from april_vision import Processor, USBCamera, calibrations, find_cameras

logger = logging.getLogger("camera_test")


def test_camera(
    output_writer: csv.DictWriter,
    collect_asset: bool,
    vidpid_filter: List[str],
    marker_id: int,
    marker_size: float = 80,
) -> None:
    """Test a camera."""
    cam: Optional[Processor] = None
    results: Dict[str, Any] = {}

    # Find available cameras
    all_cameras = find_cameras(calibrations, include_uncalibrated=True)
    if vidpid_filter:
        cameras = [camera for camera in all_cameras if camera.vidpid in vidpid_filter]
    else:
        cameras = all_cameras

    if not cameras:
        raise AssertionError("No cameras found")
    if len(cameras) > 1:
        logger.warning("Multiple cameras found, using the first one")

    camera = cameras[0]
    if camera.calibration is None:
        logger.warning("Camera lacks calibration data. No distance measurement possible.")

    try:
        results['passed'] = False  # default to failure

        results['serial'] = camera.serial_num
        logger.info(f"Camera serial number: {camera.serial_num}")

        if collect_asset:
            asset_tag = input("Enter the asset tag: ")
            results['asset'] = asset_tag

        if camera.calibration is None:
            source = USBCamera(camera.index, (1280, 720))
        else:
            source = USBCamera.from_calibration_file(
                camera.index,
                camera.calibration,
                camera.vidpid,
            )

        logger.info(f"Camera {camera.name} ({camera.serial_num}) opened, index {camera.index}")
        logger.info(f"Resolution set to {source._get_resolution()}")  # noqa: SLF001

        cam = Processor(
            source,
            tag_sizes=float(marker_size) / 1000,
            calibration=source.calibration,
        )
        logger.info("Press 'q' to quit the preview window")

        marker_detected = False
        while True:
            frame = cam._capture(fresh=False)  # noqa: SLF001
            cv2.imshow('image', frame.colour_frame)
            button = cv2.waitKey(1) & 0xFF
            if (button == ord('q')) or (button == 27):
                cv2.destroyAllWindows()
                _ = cv2.waitKey(1)  # Window is only closed after this wait
                # Quit on q or ESC key
                raise AssertionError("Camera test aborted by user")

            markers = cam.see(frame=frame.colour_frame)

            for marker in markers:
                if marker.id == marker_id:
                    marker_detected = True
                    break
                else:
                    logger.warning(f"Detected unexpected marker ID: {marker.id}")

            if marker_detected:
                break

        # On detecting the correct marker, annotate it and stop updating the preview
        cam._annotate(frame, [marker])  # noqa: SLF001
        cv2.imshow('image', frame.colour_frame)

        if marker.has_pose():
            distance = marker.distance
            results['distance'] = distance
            logger.info(f"Detected marker ID: {marker.id} at distance {distance:.0f} mm")
        else:
            logger.info(f"Detected marker ID: {marker.id}")

        logger.info("Press any key to continue")

        # Any key closes the preview window
        _ = cv2.waitKey(0)
        cv2.destroyAllWindows()
        _ = cv2.waitKey(1)

        logger.info("Camera passed")
        results['passed'] = True
    finally:
        output_writer.writerow(results)
        if cam is not None:
            cam.close()


def main(args: argparse.Namespace) -> None:
    """Main function for the camera test."""
    new_log = True
    fieldnames = ['asset', 'serial', 'passed', 'distance']

    vidpid_filter = [vidpid.lower() for vidpid in args.vidpid_filter]

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
                test_camera(
                    writer,
                    args.collect_asset,
                    vidpid_filter,
                    args.marker_id,
                    args.marker_size,
                )
            except AssertionError as e:
                logger.error(f"Test failed: {e}")

            result = input("Test another camera? [Y/n]") or 'y'
            if result.lower() != 'y':
                break

    logger.info(f"Test results saved to {logfile}")


def create_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Camera command parser."""
    parser = subparsers.add_parser(
        "camera",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__),
        help="Test a camera. Requires a printed AprilTag marker.",
    )

    parser.add_argument('--log', default=None, help='A CSV file to save test results to.')
    parser.add_argument('--collect-asset', action='store_true',
                        help='Collect the asset tag from the camera.')
    parser.add_argument('--vidpid-filter', default=['046d:0825'], nargs='+',
                        help='USB VID and PID filter for the camera. '
                             'Format: VID:PID, e.g. 1234:5678')
    parser.add_argument('--marker-id', type=int, default=101,
                        help='AprilTag marker ID to detect. Default is 101.')
    parser.add_argument('--marker-size', type=float, default=80,
                        help='Size of the AprilTag marker in mm. Default is 80 mm.')

    parser.set_defaults(func=main)
