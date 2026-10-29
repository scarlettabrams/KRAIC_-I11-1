import os
import threading
import time
from datetime import datetime

import cv2
from helper.helper import (
    load_json,
    update_json,
)

# ======================================================================================

# Important Constants

# ======================================================================================

# This must match the top-camera key in connection_settings.json.
TOP_CAMERA_DEVICE_TYPE = "FLIR_Camera_Top"

# Hardcoded software ROI within the full-sized top-camera image.
# Replace these values with the correct location for your setup.
TRIGGER_ROI_X = 1000
TRIGGER_ROI_Y = 0
TRIGGER_ROI_WIDTH = 16
TRIGGER_ROI_HEIGHT = 2048

TRIGGER_SAMPLE_SECONDS = 10.0

# Prevents noise around the threshold from being counted as
# multiple separate crossings.
TRIGGER_HYSTERESIS = 5.0


def calculate_test_video_duration(
    distance_mm,
    speed_mm_s,
    buffer_seconds=0.0,
):
    """Calculate recording duration from stage distance and speed."""

    if speed_mm_s <= 0:
        raise ValueError("Stage speed must be greater than zero.")

    duration = (float(distance_mm) / float(speed_mm_s)) + float(buffer_seconds)

    return duration


def record_both_cameras(
    top_camera,
    plane_camera,
    img_folder_path,
    duration_seconds,
    top_fps,
    plane_fps,
    repeats,
):
    """Record both cameras for the same requested duration.

    Returns True when both videos complete without an error.
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    top_filename = os.path.join(
        img_folder_path,
        f"{timestamp}_top_camera_{repeats:03d}.avi",
    )

    plane_filename = os.path.join(
        img_folder_path,
        f"{timestamp}_plane_camera_{repeats:03d}.avi",
    )

    start_event = threading.Event()
    stop_event = threading.Event()

    # Two workers plus this controlling thread.
    ready_barrier = threading.Barrier(3)

    errors = []

    top_thread = threading.Thread(
        target=video_camera_worker,
        kwargs={
            "camera": top_camera,
            "filename": top_filename,
            "video_fps": top_fps,
            "start_event": start_event,
            "stop_event": stop_event,
            "ready_barrier": ready_barrier,
            "errors": errors,
        },
        name="TopCameraVideo",
    )

    plane_thread = threading.Thread(
        target=video_camera_worker,
        kwargs={
            "camera": plane_camera,
            "filename": plane_filename,
            "video_fps": plane_fps,
            "start_event": start_event,
            "stop_event": stop_event,
            "ready_barrier": ready_barrier,
            "errors": errors,
        },
        name="PlaneCameraVideo",
    )

    top_thread.start()
    plane_thread.start()

    try:
        # Wait until both cameras have supplied a first frame and
        # both video writers are ready.
        ready_barrier.wait()

        recording_start = time.perf_counter()

        # Release both camera workers together.
        start_event.set()

        print("\nBoth video recordings started.")

        while time.perf_counter() - recording_start < duration_seconds:
            time.sleep(0.01)

    except threading.BrokenBarrierError:
        pass

    finally:
        # Both workers see the same stop signal.
        stop_event.set()
        start_event.set()

        top_thread.join()
        plane_thread.join()

    if errors:
        print("\nVideo recording errors:")

        for error in errors:
            print(error)

        return False

    print("\nBoth video recordings stopped.")
    print(f"Top video: {top_filename}")
    print(f"Plane video: {plane_filename}")

    return True


def video_camera_worker(
    camera,
    filename,
    video_fps,
    start_event,
    stop_event,
    ready_barrier,
    errors,
):
    """
    Record one camera between the shared start and stop events.
    """

    writer = None

    try:
        first_frame = None

        while first_frame is None:
            first_frame = get_camera_frame(camera)

        first_frame = prepare_video_frame(first_frame)

        height, width = first_frame.shape[:2]

        fourcc = cv2.VideoWriter.fourcc(*"XVID")

        writer = cv2.VideoWriter(
            filename,
            fourcc,
            float(video_fps),
            (width, height),
        )

        if not writer.isOpened():
            raise RuntimeError(f"Could not open video writer: {filename}")

        # Tell the controller that this camera is ready.
        ready_barrier.wait()

        # Both workers wait for the same start command.
        start_event.wait()

        writer.write(first_frame)

        while not stop_event.is_set():
            frame = get_camera_frame(camera)

            if frame is None:
                continue

            writer.write(prepare_video_frame(frame))

    except Exception as error:
        errors.append(f"{os.path.basename(filename)}: {error}")

        stop_event.set()
        start_event.set()

        try:
            ready_barrier.abort()
        except Exception:
            pass

    finally:
        if writer is not None:
            writer.release()


def prepare_video_frame(frame):
    """Convert a camera frame into an OpenCV video frame."""

    if len(frame.shape) == 2:
        return cv2.cvtColor(
            frame,
            cv2.COLOR_GRAY2BGR,
        )

    return frame


def get_camera_frame(camera, timeout_ms=1000):
    """
    Retrieve and copy one complete frame.

    Returns None when an incomplete frame is received.
    """

    image_result = camera.GetNextImage(timeout_ms)

    try:
        if image_result.IsIncomplete():
            return None

        return image_result.GetNDArray().copy()

    finally:
        image_result.Release()


def wait_for_live_trigger(
    top_camera,
    threshold,
    pair_time,
):
    """
    Monitor the top-camera software ROI until a valid pair of
    high-to-low threshold crossings is detected.

    Returns True immediately when the second trough of a valid
    close pair is detected.
    """

    armed = False
    inside_trough = False
    first_crossing_time = None

    reset_level = threshold + TRIGGER_HYSTERESIS

    roi_x_end = TRIGGER_ROI_X + TRIGGER_ROI_WIDTH
    roi_y_end = TRIGGER_ROI_Y + TRIGGER_ROI_HEIGHT

    print("\nWaiting for live trigger...")

    while True:
        image_result = top_camera.GetNextImage(1000)

        try:
            if image_result.IsIncomplete():
                continue

            frame = image_result.GetNDArray()

            frame_height, frame_width = frame.shape[:2]

            if (
                TRIGGER_ROI_X < 0
                or TRIGGER_ROI_Y < 0
                or roi_x_end > frame_width
                or roi_y_end > frame_height
            ):
                raise ValueError(
                    "The hardcoded trigger ROI lies outside the top-camera image."
                )

            roi = frame[
                TRIGGER_ROI_Y:roi_y_end,
                TRIGGER_ROI_X:roi_x_end,
            ]

            intensity = float(roi.mean())
            now = time.perf_counter()

            # Ignore a partial trough that is already present when
            # live monitoring begins. Detection is armed only after
            # the intensity is observed in its recovered/high state.
            if not armed:
                if intensity >= reset_level:
                    armed = True

                continue

            # Detect a high-to-low crossing.
            if not inside_trough:
                if intensity <= threshold:
                    inside_trough = True

                    if first_crossing_time is None:
                        first_crossing_time = now

                    else:
                        crossing_gap = now - first_crossing_time

                        if crossing_gap <= pair_time:
                            print("Valid trigger pair detected.")
                            return True

                        # Previous trough was too far away.
                        # Current trough becomes the first trough
                        # of a possible new pair.
                        first_crossing_time = now

            # The signal must recover before another trough can
            # be recognised.
            elif intensity >= reset_level:
                inside_trough = False

        finally:
            image_result.Release()


def repeats(speed, conn_settings, img_settings, img_folder_path):

    while True:
        img_json = load_json(img_settings)

        folder_name = os.path.basename(os.path.normpath(img_folder_path))

        run_speed = float(
            img_json["IMAGING_SETTINGS"][folder_name].get("run_speed", 0.1)
        )
        return_speed = float(
            img_json["IMAGING_SETTINGS"][folder_name].get("return_speed", 1)
        )
        repeats = img_json["IMAGING_SETTINGS"][folder_name].get("repeats", 1)
        delay = float(img_json["IMAGING_SETTINGS"][folder_name].get("delay", 0))

        run_speed_mm = run_speed * 60
        return_speed_mm = return_speed * 60

        print(
            f"\nRun speed: {round(run_speed_mm, 2)}mm/s"
            f"\nReturn speed: {round(return_speed_mm, 2)}mm/s"
            f"\nRepeats: {repeats}"
            f"\nDelay: {delay}\n"
        )

        confirm = input("Begin run with previous settings(y/n): ")

        if confirm not in ("y", "n"):
            print("Invalid response: please select y/n")
            continue

        if confirm == "y":
            return run_speed, return_speed, repeats, delay

        while True:
            print(f"Current repeats:{repeats}")
            response1 = input(
                "Would you like to change the current number of repeats(y/n)"
            ).strip()

            if response1 not in ("y", "n"):
                print("Invalid response: please select y/n")
                continue

            if response1 == "n":
                break

            repeats_response = input("How many repeats would you like to do? ")

            try:
                repeats_int = int(repeats_response)
                img_json["IMAGING_SETTINGS"][folder_name]["repeats"] = repeats_int
                break

            except ValueError as e:
                print(f"Error: {e}\n\n Please input an integer")
                continue

        while True:
            print(f"Current run speed:{run_speed_mm}mm/s")
            run_speed_response = input(
                "Would you like to change the current speed(y/n)"
            )

            if run_speed_response not in ("y", "n"):
                print("Invalid response: please select y/n")
                continue

            elif run_speed_response == "n":
                break

            new_speed_mm = input("Please input new speed between 0-20mm/s: ")

            try:
                speed_float = float(new_speed_mm)

            except ValueError as e:
                print(f"Error: {e}\n\n Please input an number")
                continue

            if speed_float > 20 or speed_float < 0:
                print("selected speed is outside of limits, try again")
                continue

            speed_rev = speed_float / 60

            img_json["IMAGING_SETTINGS"][folder_name]["run_speed"] = speed_rev

            break

        while True:
            print(f"Current return speed:{return_speed_mm}mm/s")
            return_speed_response = input(
                "Would you like to change the current return speed(y/n)"
            )

            if return_speed_response not in ("y", "n"):
                print("Invalid response: please select y/n")
                continue

            elif return_speed_response == "n":
                break

            new_return_mm = input("Please input new speed between 0-80mm/s: ")

            try:
                return_float = float(new_return_mm)

            except ValueError as e:
                print(f"Error: {e}\n\n Please input an number")
                continue

            if return_float > 80 or return_float < 0:
                print("selected speed is outside of limits, try again")
                continue

            return_rev = return_float / 60

            img_json["IMAGING_SETTINGS"][folder_name]["return_speed"] = return_rev

            break

        while True:
            print(f"Current delay:{delay}s")
            return_delay = input("Would you like to change the current delay(y/n)")

            if return_delay not in ("y", "n"):
                print("Invalid response: please select y/n")
                continue

            elif return_delay == "n":
                break

            new_return_delay = input("Please input new delay (0-2): ")

            try:
                delay_float = float(new_return_delay)

            except ValueError as e:
                print(f"Error: {e}\n\n Please input an number")
                continue

            if delay_float > 2 or delay_float < 0:
                print("selected delay is outside of limits, try again")
                continue

            img_json["IMAGING_SETTINGS"][folder_name]["delay"] = delay_float

            break

        update_json(img_settings, img_json)
