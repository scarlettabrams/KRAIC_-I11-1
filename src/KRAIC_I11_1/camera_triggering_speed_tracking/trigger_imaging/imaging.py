import os
import time
from datetime import datetime

from communication.software_communication import PyConnection
from helper.helper import (
    list_dict,
    load_json,
    update_json,
)
from imaging.lets_move import (
    calculate_test_video_duration,
    record_both_cameras,
    repeats,
    wait_for_live_trigger,
)
from imaging.trigger import (
    capture_trigger_data,
    input_pair_time,
    input_trigger_threshold,
    load_trigger_settings,
    plot_trigger_calibration,
    save_trigger_settings,
)
from individual_equipment_control_menu.equipment.cam_vision import (
    configure_continuous_acquisition,
    get_camera,
    release_camera,
)

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import PySpin
except ImportError:
    PySpin = None

_flir_system = None
_flir_cam_list = None

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

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


# ======================================================================================

# The Main Menu

# ======================================================================================


def img_menu(img_root_folder, conn_settings, img_settings):
    """Allows the user to start a new imaging run or go into a current run"""

    while True:
        imaging_folders = []

        for item in os.listdir(img_root_folder):
            imaging_folders.append(item)

        end_tags = ["Begin New Imaging Experiment", "Return to KRAIC Menu"]

        user_options = imaging_folders + end_tags

        i = 1
        keys = []
        while i <= len(user_options):
            keys.append(str(i))
            i = i + 1

        user_dict = dict(zip(keys, user_options, strict=False))

        list_dict("Imaging Options", user_dict)

        selection = input(
            "\nPlease choose an imaging option by selecting a number from the list "
            "above: "
        )

        if selection == str(len(user_options) - 1):
            folder_name = create_img_folder(img_root_folder)
            create_json(img_settings, folder_name)

            print("Please select new image folder")

        elif selection == str(len(user_options)):
            print("\nReturning to Main Menu")
            break

        elif selection in user_dict:
            img_folder_name = user_dict[selection]
            img_folder_path = os.path.join(img_root_folder, img_folder_name)

            image_crystals(img_folder_path, conn_settings, img_settings)

        else:
            print(f"'{selection}' is an invalid selection, please try again")
            continue


# ======================================================================================

# New Experiment

# ======================================================================================


def create_img_folder(img_root_folder):
    """begin creating the file structure"""

    while True:
        print("The new folder name will already be timestamped\n")
        fingerprint = input(
            "Please add something to the folder title to make it more easily "
            "identifiable."
        )

        confirm = (
            input(
                f"Would you like to add the following to the title: {fingerprint} (y/n)"
            )
            .strip()
            .lower()
        )

        if confirm not in ("y", "n"):
            print("\nPlease select y/n")
            continue

        if confirm == "n":
            continue

        now = datetime.now()
        stamp = f"{now.day}_{now.month}_{now.year}_{now.hour}_{now.minute}"
        folder_name = f"{stamp}_{fingerprint}_Imaging_Folder"
        folder_path = os.path.join(img_root_folder, folder_name)

        print(f"Folder path: {folder_path}")

        os.makedirs(folder_path, exist_ok=True)

        return folder_name


def create_json(img_settings, folder_name):
    """create new location within the json"""

    img_json = load_json(img_settings)

    if "IMAGING_SETTINGS" not in img_json:
        img_json["IMAGING_SETTINGS"] = {}

    if folder_name not in img_json["IMAGING_SETTINGS"]:
        img_json["IMAGING_SETTINGS"][folder_name] = {
            "trigger_threshold": 1.0,
            "pair_time": 1.0,
            "run_speed": 0.1,
            "return_speed": 1,
            "repeats": 1,
            "delay": 0,
        }

    update_json(img_settings, img_json)


def load_motion_settings(img_folder_path, img_settings):
    """Load the pair time and current threshold values."""

    img_json = load_json(img_settings)

    folder_name = os.path.basename(os.path.normpath(img_folder_path))

    experiment_settings = img_json.get("IMAGING_SETTINGS", {}).get(folder_name, {})

    run_speed = float(experiment_settings.get("run_speed", 0.1))

    return_speed = float(experiment_settings.get("return_speed", 1.0))

    repeats = int(experiment_settings.get("repeats", 1))

    delay = int(experiment_settings.get("delay", 1))

    return run_speed, return_speed, repeats, delay


# ======================================================================================

# Image Crystals using both cameras

# ======================================================================================


def image_crystals(img_folder_path, conn_settings, img_settings):
    """for imaging crystals and changing settings of camera"""

    while True:
        (
            plane_cam_settings,
            top_cam_settings,
            plane_settings,
            top_settings,
            main_settings,
        ) = query_settings(conn_settings)

        print("\nStereoscopic Imaging Menu\n")

        options = {
            "1": "Current Settings",
            "2": "Triggering",
            "3": "Test Run",
            "4": "Begin Capture",
            "5": "Exit to Main Menu",
        }

        for number, option in options.items():
            print(f"{number}: {option}")

        selection = input(
            "\nPlease select an option from the list above by selecting a number: "
        ).strip()

        if selection not in options:
            print(
                f"'{selection}' is an invalid selection: please select another option "
                "from the list above"
            )
            continue

        if selection == "5":
            print("Returning to Main Menu")
            break

        elif selection == "1":
            retrieve_settings(
                plane_cam_settings,
                top_cam_settings,
                plane_settings,
                top_settings,
                main_settings,
            )

        elif selection == "2":
            triggering(img_folder_path, conn_settings, img_settings)

        elif selection == "3":
            repeats(main_settings[3], conn_settings, img_settings, img_folder_path)
            if repeats:
                run(
                    img_folder_path,
                    conn_settings,
                    img_settings,
                    main_settings[6],
                    top_cam_settings[0],
                    plane_cam_settings[0],
                    main_settings[2],
                )
            else:
                print("Run Aborted")

        elif selection == "4":
            repeats(main_settings[3], conn_settings, img_settings, img_folder_path)
            if repeats:
                run(
                    img_folder_path,
                    conn_settings,
                    img_settings,
                    main_settings[6],
                    top_cam_settings[0],
                    plane_cam_settings[0],
                    main_settings[2],
                )
            else:
                print("Run Aborted")


def query_settings(conn_settings):
    """The pieces of equipment that are being used on this occasion are

    - FLIR_Camera_Bottom (FPS, exposure time, gain)
    - FLIR_Camera_Top (FPS, exposure time, gain)
    - Focus_and_Lights (speed,acc,lim, LED Intensity)
    - KRAIC-Analysis (speed,acc,lim,)

    so we need to retrieve the settings for each

    """

    with PyConnection("Focus_and_Lights", conn_settings) as conn:
        plane_camera_q = conn.send_serial("Q 1")

    with PyConnection("Focus_and_Lights", conn_settings) as conn:
        top_camera_q = conn.send_serial("Q 2")

    with PyConnection("KRAIC-Analysis", conn_settings) as conn:
        main_motion_q = conn.send_serial("Q")

    plane_settings = query_plane(plane_camera_q)
    top_settings = query_top(top_camera_q)
    main_settings = query_main(main_motion_q)

    plane_cam_settings = query_cam("FLIR_Camera_Plane", conn_settings)
    top_cam_settings = query_cam("FLIR_Camera_Top", conn_settings)

    return (
        plane_cam_settings,
        top_cam_settings,
        plane_settings,
        top_settings,
        main_settings,
    )


def retrieve_settings(pcs, tcs, ps, ts, ms):
    """Making a nice display table from the settings"""

    print("\nMOTOR SETTINGS\n\n")

    print(
        "MOTION DIRECTION\t||\tCURRENT POSITION(mm)\t||\tLOW LIMIT(mm)\t||\tHIGH "
        "LIMIT(mm)\t||\tSPEED(mm/s)\t||\tACC(mm/s^2)\t||\tLED(%) "
    )
    print(
        f"Plane\t||\t{ps[0]}\t||\t{ps[1]}\t||\t{ps[2]}\t||\t{ps[3]}\t||\t{ps[4]}\t||\t{ps[5]}"
    )
    print(
        f"Top\t||\t{ts[0]}\t||\t{ts[1]}\t||\t{ts[2]}\t||\t{ts[3]}\t||\t{ts[4]}\t||\t{ts[5]}"
    )
    print(
        f"Main\t||\t{ms[0]}\t||\t{ms[1]}\t||\t{ms[2]}\t||\t{ms[3]}\t||\t{ms[4]}\t||\t---"
    )

    print("\n\nCAMERA SETTINGS\n\n")

    print("ORIENTATION\t||\tFPS\t||\tGAIN(dB)\t||\tEXPOSURE TIME(µs)")
    print(f"Plane\t||\t{pcs[0]}\t||\t{pcs[1]}\t||\t{pcs[2]}")
    print(f"Top\t||\t{tcs[0]}\t||\t{tcs[1]}\t||\t{tcs[2]}")


def parse_query_response(response):
    """Convert a space-separated controller response into a dictionary."""

    if not response:
        raise ValueError("Empty controller response")

    values = {}

    for item in response.split():
        if "=" not in item:
            continue

        key, value = item.split("=", 1)
        values[key] = value

    return values


def query_top(response):
    """Convert top-axis controller values into mm units."""

    values = parse_query_response(response)

    pos_mm = round(float(values["POS_REV"]) * 0.5, 2)
    low_mm = round(float(values["LIM_LOW"]) * 0.5, 2)
    high_mm = round(float(values["LIM_HIGH"]) * 0.5, 2)
    speed_mm = round(float(values["SPEED_REV_S"]) * 0.5, 2)
    acc_mm = round(float(values["ACC_REV_S2"]) * 0.5, 2)
    led_t = int(values["LED2"])

    return [
        pos_mm,
        low_mm,
        high_mm,
        speed_mm,
        acc_mm,
        led_t,
    ]


def query_plane(response):
    """Convert plane-axis controller values into mm units."""

    values = parse_query_response(response)

    pos_mm = round(float(values["POS_REV"]) * 0.5, 2)
    low_mm = round(float(values["LIM_LOW"]) * 0.5, 2)
    high_mm = round(float(values["LIM_HIGH"]) * 0.5, 2)
    speed_mm = round(float(values["SPEED_REV_S"]) * 0.5, 2)
    acc_mm = round(float(values["ACC_REV_S2"]) * 0.5, 2)
    led_p = int(values["LED1"])

    return [
        pos_mm,
        low_mm,
        high_mm,
        speed_mm,
        acc_mm,
        led_p,
    ]


def query_main(response):
    """Convert main-stage controller values into mm units."""

    values = parse_query_response(response)

    pos_mm = round(float(values["POS_REV"]) * 60, 2)
    low_mm = round(float(values["LIM_LOW"]) * 60, 2)
    high_mm = round(float(values["LIM_HIGH"]) * 60, 2)
    speed_mm = round(float(values["SPEED_REV_S"]) * 60, 2)
    acc_mm = round(float(values["ACC_REV_S2"]) * 60, 2)

    speed_rev = float(values["SPEED_REV_S"])
    high_rev = float(values["LIM_HIGH"])

    return [
        pos_mm,
        low_mm,
        high_mm,
        speed_mm,
        acc_mm,
        speed_rev,
        high_rev,
    ]


def query_cam(device_type, conn_settings):
    """
    Returns the current FPS, gain and exposure time
    for the selected FLIR camera.
    """

    if PySpin is None:
        print("PySpin could not be imported.")
        return [None]

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return [None]

    try:
        camera.Init()

        node_map = camera.GetNodeMap()

        fps = PySpin.CFloatPtr(node_map.GetNode("AcquisitionFrameRate"))

        gain = PySpin.CFloatPtr(node_map.GetNode("Gain"))

        exposure = PySpin.CFloatPtr(node_map.GetNode("ExposureTime"))

        fps_value = (
            round(fps.GetValue(), 2) if PySpin.IsReadable(fps) else "Unavailable"
        )

        gain_value = (
            round(gain.GetValue(), 2) if PySpin.IsReadable(gain) else "Unavailable"
        )

        exposure_value = (
            round(exposure.GetValue(), 2)
            if PySpin.IsReadable(exposure)
            else "Unavailable"
        )

        return [fps_value, gain_value, exposure_value]

    except Exception as e:
        print(f"Could not query camera settings: {e}")
        return [None]

    finally:
        release_camera(
            system,
            cam_list,
            camera,
        )


def triggering(img_folder_path, conn_settings, img_settings):
    """
    Capture ten seconds of top-camera intensity data and allow
    the user to calibrate threshold and pair-time settings.
    """

    if plt is None:
        print("Matplotlib could not be imported. Please install matplotlib.")
        return

    times, intensities = capture_trigger_data(conn_settings)

    if not times or not intensities:
        print("No valid trigger data was collected.")
        return

    threshold, pair_time = load_trigger_settings(img_folder_path, img_settings)

    while True:
        crossing_indices, valid_trigger_indices = plot_trigger_calibration(
            times=times,
            intensities=intensities,
            threshold=threshold,
            pair_time=pair_time,
        )

        print("\nCurrent Trigger Settings\n")
        print(f"Threshold: {threshold:.2f}")
        print(f"Pair time: {pair_time:.3f} seconds")
        print(f"Threshold crossings: {len(crossing_indices)}")
        print(f"Valid triggers: {len(valid_trigger_indices)}")

        options = {
            "1": "Change Threshold",
            "2": "Change Pair Time",
            "3": "Redraw Graph",
            "4": "Capture Another 10 Seconds",
            "5": "Save and Return",
        }

        print("\nTrigger Calibration Options\n")

        for number, option in options.items():
            print(f"{number}: {option}")

        selection = input("\nPlease select an option: ").strip()

        if selection == "1":
            threshold = input_trigger_threshold()

        elif selection == "2":
            pair_time = input_pair_time()

        elif selection == "3":
            continue

        elif selection == "4":
            new_times, new_intensities = capture_trigger_data(conn_settings)

            if new_times and new_intensities:
                times = new_times
                intensities = new_intensities

        elif selection == "5":
            save_trigger_settings(
                img_folder_path=img_folder_path,
                img_settings=img_settings,
                threshold=threshold,
                pair_time=pair_time,
            )
            return

        else:
            print(f"'{selection}' is an invalid selection.")


def run(
    img_folder_path,
    conn_settings,
    img_settings,
    distance,
    fps_top,
    fps_plane,
    distance_mm,
):
    """
    Perform one live-triggered forward test run.

    Camera FPS, gain and exposure time are not changed here. The current
    values set through individual equipment control are used.
    """

    i = 0

    if PySpin is None:
        print("PySpin could not be imported.")
        return

    if cv2 is None:
        print("OpenCV could not be imported.")
        return

    threshold, pair_time = load_trigger_settings(img_folder_path, img_settings)

    run_speed, return_speed, repeats, delay = load_motion_settings(
        img_folder_path, img_settings
    )

    run_speed_mm = run_speed * 60

    return_speed_mm = return_speed * 60

    before_repeats_speed = 0.5

    recording_buffer_seconds = (
        0  # we can change this value to make sure our vids are spot on for time
    )

    duration_seconds = calculate_test_video_duration(
        distance_mm, run_speed_mm, buffer_seconds=recording_buffer_seconds
    )
    print(f"run time:{duration_seconds}")
    return_duration_seconds = calculate_test_video_duration(
        distance_mm, return_speed_mm, buffer_seconds=5
    )
    print(f"return time:{return_duration_seconds}")

    run_speed_command = f"SPEED {run_speed}"
    return_speed_command = f"SPEED {return_speed}"

    system, cam_list, top_camera = get_camera("FLIR_Camera_Top", conn_settings)

    system, cam_list, plane_camera = get_camera(
        "FLIR_Camera_Plane",
        conn_settings,
    )

    with PyConnection("KRAIC-Analysis", conn_settings) as conn:
        response = conn.send_serial(before_repeats_speed)

    print("Ensuring stage is at zero position")

    with PyConnection("KRAIC-Analysis", conn_settings) as conn:
        response = conn.send_serial("GOTO 0")

    print(f"{response}")

    time.sleep(12)

    if top_camera is None or plane_camera is None:
        print("Could not access both cameras.")

        return

    while i < repeats:
        try:
            with PyConnection("KRAIC-Analysis", conn_settings) as conn:
                response = conn.send_serial(run_speed_command)
            time.sleep(2)
            print(f"\nRun speed set: {run_speed_mm}")

            i = i + 1

            print(f"\nRepeat Number: {i}")

            top_camera.Init()

            plane_camera.Init()

            if not configure_continuous_acquisition(top_camera):
                return
            if not configure_continuous_acquisition(plane_camera):
                return

            top_camera.BeginAcquisition()

            trigger_detected = wait_for_live_trigger(
                top_camera=top_camera, threshold=threshold, pair_time=pair_time
            )

            if not trigger_detected:
                print("Trigger monitoring ended without a trigger.")
                return

            trigger_time = time.perf_counter()

            # ==========================================================
            # MOVEMENT COMMAND POSITIVE

            time.sleep(delay)

            command = f"GOTO {distance}"

            with PyConnection("KRAIC-Analysis", conn_settings) as conn:
                response = conn.send_serial(command)
            # ==========================================================

            movement_command_time = time.perf_counter()

            print(
                "Movement command section reached "
                f"{(movement_command_time - trigger_time) * 1000:.2f} ms after trigger "
                "detection."
            )

            # Begin plane-camera acquisition only after the movement
            # command has been issued.
            plane_camera.BeginAcquisition()

            record_both_cameras(
                top_camera=top_camera,
                plane_camera=plane_camera,
                img_folder_path=img_folder_path,
                duration_seconds=duration_seconds,
                top_fps=fps_top,
                plane_fps=fps_plane,
                repeats=i,
            )
            if top_camera.IsStreaming():
                top_camera.EndAcquisition()
            if plane_camera.IsStreaming():
                plane_camera.EndAcquisition()

            print("Test run complete.")

        except Exception as error:
            print(f"Test run error: {error}")
            i = 200000
            break

        finally:
            try:
                if top_camera.IsStreaming():
                    top_camera.EndAcquisition()
            except Exception:
                pass

            try:
                if plane_camera.IsStreaming():
                    plane_camera.EndAcquisition()
            except Exception:
                pass
                release_camera(system, cam_list, top_camera)
                release_camera(system, cam_list, plane_camera)

            # ==========================================================
            # MOVEMENT COMMAND NEGATIVE

            with PyConnection("KRAIC-Analysis", conn_settings) as conn:
                conn.send_serial(return_speed_command)

            with PyConnection("KRAIC-Analysis", conn_settings) as conn:
                response = conn.send_serial("GOTO 0")

            print(f"Returning to start: {response}")

            time.sleep(return_duration_seconds)

            # ==========================================================
