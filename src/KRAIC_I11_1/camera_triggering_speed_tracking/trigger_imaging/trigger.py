import os
import time

import matplotlib.pyplot as plt

from KRAIC_I11_1.camera_triggering_speed_tracking.trigger_imaging.imaging import (
    configure_continuous_acquisition,
    get_camera,
    release_camera,
)
from KRAIC_I11_1.utils.helper import (
    load_json,
    update_json,
)

_flir_system = None
_flir_cam_list = None


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


def capture_trigger_data(conn_settings):
    """
    Capture ten seconds of intensity measurements from the
    hardcoded software ROI on the full-sized top-camera frames.
    """

    system, cam_list, camera = get_camera(
        TOP_CAMERA_DEVICE_TYPE,
        conn_settings,
    )

    if camera is None:
        print("Could not access the top camera.")
        return None, None

    times = []
    intensities = []

    try:
        camera.Init()

        if not configure_continuous_acquisition(camera):
            return None, None

        camera.BeginAcquisition()

        print(f"\nCollecting trigger data for {TRIGGER_SAMPLE_SECONDS:.0f} seconds...")

        start_time = time.perf_counter()

        while True:
            elapsed = time.perf_counter() - start_time

            if elapsed >= TRIGGER_SAMPLE_SECONDS:
                break

            image_result = camera.GetNextImage(1000)

            try:
                if image_result.IsIncomplete():
                    print(
                        f"Incomplete image with status {image_result.GetImageStatus()}"
                    )
                    continue

                frame = image_result.GetNDArray()

                frame_height, frame_width = frame.shape[:2]

                roi_x_end = TRIGGER_ROI_X + TRIGGER_ROI_WIDTH

                roi_y_end = TRIGGER_ROI_Y + TRIGGER_ROI_HEIGHT

                if (
                    TRIGGER_ROI_X < 0
                    or TRIGGER_ROI_Y < 0
                    or roi_x_end > frame_width
                    or roi_y_end > frame_height
                ):
                    raise ValueError(
                        "The hardcoded trigger ROI is outside "
                        "the top-camera image.\n"
                        f"Frame size: {frame_width} x "
                        f"{frame_height}\n"
                        f"ROI: x={TRIGGER_ROI_X}, "
                        f"y={TRIGGER_ROI_Y}, "
                        f"width={TRIGGER_ROI_WIDTH}, "
                        f"height={TRIGGER_ROI_HEIGHT}"
                    )

                roi = frame[
                    TRIGGER_ROI_Y:roi_y_end,
                    TRIGGER_ROI_X:roi_x_end,
                ]

                mean_intensity = float(roi.mean())

                times.append(elapsed)
                intensities.append(mean_intensity)

            finally:
                image_result.Release()

    except Exception as error:
        print(f"Trigger data collection error: {error}")
        return None, None

    finally:
        try:
            if camera.IsStreaming():
                camera.EndAcquisition()
        except Exception:
            pass

        release_camera(
            system,
            cam_list,
            camera,
        )

    print(f"Collected {len(intensities)} intensity measurements.")

    return times, intensities


def load_trigger_settings(img_folder_path, img_settings):
    """Load the pair time and current threshold values."""

    img_json = load_json(img_settings)

    folder_name = os.path.basename(os.path.normpath(img_folder_path))

    experiment_settings = img_json.get("IMAGING_SETTINGS", {}).get(folder_name, {})

    threshold = float(experiment_settings.get("trigger_threshold", 1.0))

    pair_time = float(experiment_settings.get("pair_time", 1.0))

    return threshold, pair_time


def plot_trigger_calibration(
    times,
    intensities,
    threshold,
    pair_time,
):
    """Plot trigger calibration data using the current settings."""

    crossing_indices = find_threshold_crossings(
        times=times,
        intensities=intensities,
        threshold=threshold,
    )

    valid_trigger_indices = identify_valid_pair_triggers(
        times=times,
        crossing_indices=crossing_indices,
        pair_time=pair_time,
    )

    if plt is None:
        print("Matplotlib could not be imported. Please install matplotlib.")
        return crossing_indices, valid_trigger_indices

    maximum_intensity = max(intensities)

    if maximum_intensity <= 0:
        maximum_intensity = 1.0

    plt.figure(figsize=(12, 6))

    plt.plot(times, intensities, label="Mean ROI intensity")

    plt.axhline(y=threshold, linestyle="--", label=f"Threshold: {threshold:.2f}")

    for crossing_number, crossing_index in enumerate(crossing_indices, start=1):
        crossing_time = times[crossing_index]

        plt.axvline(x=crossing_time, linestyle=":", color="red", alpha=0.7)

        plt.text(
            crossing_time,
            maximum_intensity * 0.96,
            str(crossing_number),
            horizontalalignment="center",
            verticalalignment="top",
        )

    for valid_number, trigger_index in enumerate(valid_trigger_indices, start=1):
        trigger_time = times[trigger_index]
        trigger_intensity = intensities[trigger_index]

        plt.scatter(
            trigger_time,
            trigger_intensity,
            marker="o",
            s=100,
            label=("Valid second trough" if valid_number == 1 else None),
        )

        plt.text(
            trigger_time, trigger_intensity, " Trigger", verticalalignment="bottom"
        )

    for previous_index, current_index in zip(
        crossing_indices, crossing_indices[1:], strict=False
    ):
        previous_time = times[previous_index]
        current_time = times[current_index]

        time_gap = current_time - previous_time
        midpoint = (previous_time + current_time) / 2

        plt.text(
            midpoint,
            maximum_intensity * 0.82,
            f"{time_gap:.3f} s",
            horizontalalignment="center",
        )

    plt.xlabel("Time (seconds)")
    plt.ylabel("Mean ROI intensity")

    plt.title(
        "Top-camera trigger calibration\n"
        f"{len(crossing_indices)} crossings, "
        f"{len(valid_trigger_indices)} valid trigger(s)"
    )

    plt.xlim(0, max(TRIGGER_SAMPLE_SECONDS, times[-1]))

    plt.ylim(0, maximum_intensity * 1.02)

    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()

    return crossing_indices, valid_trigger_indices


def find_threshold_crossings(
    times, intensities, threshold, hysteresis=TRIGGER_HYSTERESIS
):
    """
    Detect genuine high-to-low threshold crossings.

    If monitoring begins while the signal is already below the
    threshold, that initial partial trough is ignored. Detection
    becomes armed only after the signal recovers above the reset
    level.
    """

    crossing_indices = []
    inside_trough = False
    armed = False

    reset_level = threshold + hysteresis

    for index, intensity in enumerate(intensities):
        if not armed:
            if intensity >= reset_level:
                armed = True

            continue

        if not inside_trough:
            if intensity <= threshold:
                crossing_indices.append(index)
                inside_trough = True

        elif intensity >= reset_level:
            inside_trough = False

    return crossing_indices


def identify_valid_pair_triggers(times, crossing_indices, pair_time):
    """
    Identify crossings that are the second trough of a valid pair.

    Two crossings form a pair when the second crossing occurs no
    more than pair_time seconds after the first.
    """

    valid_trigger_indices = []
    first_crossing_index = None

    for crossing_index in crossing_indices:
        if first_crossing_index is None:
            first_crossing_index = crossing_index
            continue

        first_time = times[first_crossing_index]
        second_time = times[crossing_index]

        time_gap = second_time - first_time

        if time_gap <= pair_time:
            valid_trigger_indices.append(crossing_index)

            first_crossing_index = None

        else:
            first_crossing_index = crossing_index

    return valid_trigger_indices


def input_trigger_threshold():
    """Ask the user for a new threshold."""

    while True:
        raw_value = input("Please enter the new trigger threshold: ").strip()

        try:
            threshold = float(raw_value)

        except ValueError:
            print("Please enter a numerical value.")
            continue

        if threshold < 0:
            print("The threshold cannot be negative.")
            continue

        return threshold


def input_pair_time():
    """Ask the user for the maximum pair time."""

    while True:
        raw_value = input("Please enter the maximum pair time in seconds: ").strip()

        try:
            pair_time = float(raw_value)

        except ValueError:
            print("Please enter a numerical value.")
            continue

        if pair_time <= 0:
            print("Pair time must be greater than zero.")
            continue

        return pair_time


def save_trigger_settings(img_folder_path, img_settings, threshold, pair_time):
    """Save the selected threshold and pair time."""

    img_json = load_json(img_settings)

    folder_name = os.path.basename(os.path.normpath(img_folder_path))

    if "IMAGING_SETTINGS" not in img_json:
        img_json["IMAGING_SETTINGS"] = {}

    if folder_name not in img_json["IMAGING_SETTINGS"]:
        img_json["IMAGING_SETTINGS"][folder_name] = {}

    experiment_settings = img_json["IMAGING_SETTINGS"][folder_name]

    experiment_settings["trigger_threshold"] = float(threshold)

    experiment_settings["pair_time"] = float(pair_time)

    update_json(img_settings, img_json)

    print("\nTrigger settings saved")
    print(f"Threshold: {threshold:.2f}")
    print(f"Pair time: {pair_time:.3f} seconds")
