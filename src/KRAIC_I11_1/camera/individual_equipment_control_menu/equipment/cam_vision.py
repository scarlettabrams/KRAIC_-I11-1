import os
from datetime import datetime
from typing import Any

import cv2

from KRAIC_I11_1.camera.helper.helper import load_json

PySpin: Any
try:
    import PySpin
except ImportError:
    PySpin = None

_flir_system = None
_flir_cam_list = None


def flir_grasshopper_3_commands(
    device_type, conn_settings, equipment_initialisation, image_save, video_save
):
    """Defines commands for controlling the bottom FLIR Grasshopper 3 camera using
    PySpin.
    """

    print("Accessing FLIR Grasshopper 3 Bottom Camera options")

    while True:
        print("\nFLIR Grasshopper 3 Bottom Camera Menu\n")

        options = {
            "1": "Show Camera Serial",
            "2": "Live View",
            "3": "Capture Image",
            "4": "Start Video Recording",
            "5": "Change Camera Settings",
            "6": "Exit to Main Menu",
        }

        for number, option in options.items():
            print(f"{number}: {option}")

        selection = input(
            "\nPlease select an option from the list above by selecting a number: "
        )

        if selection not in options:
            print(
                f"'{selection}' is an invalid selection: please select another option "
                "from the list above"
            )
            continue

        elif selection == "6":
            print("Returning to Main Menu")
            close_flir_system()
            break

        elif selection == "1":
            show_camera_serial(device_type, conn_settings)

        elif selection == "2":
            live_view(device_type, conn_settings)

        elif selection == "3":
            capture_image(device_type, conn_settings, image_save)

        elif selection == "4":
            record_video(device_type, conn_settings, video_save)

        elif selection == "5":
            camera_settings_menu(device_type, conn_settings)


def check_libraries():
    """Checks that PySpin is available."""

    if PySpin is None:
        print(
            "PySpin could not be imported. Please install the FLIR Spinnaker SDK and "
            "matching PySpin wheel."
        )
        return False

    return True


def get_camera(device_type, conn_settings):
    global _flir_system, _flir_cam_list

    if PySpin is None:
        print("PySpin could not be imported.")
        return None, None, None

    connection = load_json(conn_settings)
    camera_serial = connection["CONNECTION_SETTINGS"][device_type].get("serial_number")

    if _flir_system is None:
        _flir_system = PySpin.System.GetInstance()

    if _flir_cam_list is None:
        _flir_cam_list = _flir_system.GetCameras()

    if _flir_cam_list.GetSize() == 0:
        print("No FLIR cameras detected")
        return None, None, None

    for i in range(_flir_cam_list.GetSize()):
        cam = _flir_cam_list.GetByIndex(i)

        node_map_tldevice = cam.GetTLDeviceNodeMap()
        serial_node = PySpin.CStringPtr(node_map_tldevice.GetNode("DeviceSerialNumber"))
        found_serial = (
            serial_node.GetValue() if PySpin.IsReadable(serial_node) else "Unknown"
        )

        if str(found_serial) == str(camera_serial):
            return _flir_system, _flir_cam_list, cam

        del cam

    print(f"Could not find camera with serial number: {camera_serial}")
    return None, None, None


def release_camera(system, cam_list, camera):
    try:
        if camera is not None and camera.IsInitialized():
            camera.DeInit()
    except Exception:
        pass

    try:
        del camera
    except Exception:
        pass

    # Do NOT call cam_list.Clear()
    # Do NOT call system.ReleaseInstance()


def show_camera_serial(device_type, conn_settings):
    """Prints the selected camera serial number."""

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return

    try:
        node_map_tldevice = camera.GetTLDeviceNodeMap()
        serial_node = PySpin.CStringPtr(node_map_tldevice.GetNode("DeviceSerialNumber"))
        model_node = PySpin.CStringPtr(node_map_tldevice.GetNode("DeviceModelName"))

        serial = serial_node.GetValue() if PySpin.IsReadable(serial_node) else "Unknown"
        model = model_node.GetValue() if PySpin.IsReadable(model_node) else "Unknown"

        print(f"\nCamera Model: {model}")
        print(f"Camera Serial: {serial}\n")

    except Exception as e:
        print(f"Could not read camera details: {e}")

    finally:
        release_camera(system, cam_list, camera)


def configure_continuous_acquisition(camera):
    """Sets camera acquisition mode to continuous."""

    node_map = camera.GetNodeMap()
    acquisition_mode = PySpin.CEnumerationPtr(node_map.GetNode("AcquisitionMode"))

    if not PySpin.IsWritable(acquisition_mode):
        print("Unable to set acquisition mode")
        return False

    continuous_mode = acquisition_mode.GetEntryByName("Continuous")
    acquisition_mode.SetIntValue(continuous_mode.GetValue())
    return True


def convert_image_to_bgr(image_result):
    """Converts a PySpin image to an OpenCV BGR array."""

    frame = image_result.GetNDArray()

    if len(frame.shape) == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    return frame


def live_view(device_type, conn_settings):
    """Shows a live view from the bottom FLIR camera. Press q to quit."""

    if not check_libraries():
        return

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return

    try:
        camera.Init()

        if not configure_continuous_acquisition(camera):
            return

        camera.BeginAcquisition()
        print("Live view started. Press 'q' in the image window to stop.")

        while True:
            image_result = camera.GetNextImage(1000)

            if image_result.IsIncomplete():
                print(
                    "Image incomplete with image status "
                    f"{image_result.GetImageStatus()}"
                )
                image_result.Release()
                continue

            frame = convert_image_to_bgr(image_result)
            image_result.Release()

            cv2.imshow("FLIR Grasshopper 3 Bottom - Live View", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        camera.EndAcquisition()
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"Live view error: {e}")

    finally:
        try:
            if camera.IsStreaming():
                camera.EndAcquisition()
        except Exception:
            pass
        cv2.destroyAllWindows()
        release_camera(system, cam_list, camera)


def capture_image(device_type, conn_settings, image_save):
    """Captures and saves a single image from the bottom FLIR camera."""

    if PySpin is None:
        print(
            "PySpin could not be imported. Please install the FLIR Spinnaker SDK and "
            "matching PySpin wheel."
        )
        return

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return

    try:
        camera.Init()

        if not configure_continuous_acquisition(camera):
            return

        camera.BeginAcquisition()
        image_result = camera.GetNextImage(1000)

        if image_result.IsIncomplete():
            print(f"Image incomplete with image status {image_result.GetImageStatus()}")
            image_result.Release()
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(image_save, f"camera_{timestamp}.png")

        frame = image_result.GetNDArray()
        cv2.imwrite(filename, frame)
        image_result.Release()

        camera.EndAcquisition()
        print(f"Image saved: {filename}")

    except Exception as e:
        print(f"Image capture error: {e}")

    finally:
        try:
            if camera.IsStreaming():
                camera.EndAcquisition()
        except Exception:
            pass
        release_camera(system, cam_list, camera)


def record_video(device_type, conn_settings, video_save):
    """Records video from the bottom FLIR camera until q is pressed."""

    if not check_libraries():
        return

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return

    video_writer = None

    try:
        while True:
            raw_fps = input("Frames per second for saved video (1-75 FPS): ")
            try:
                fps = float(raw_fps)
                if fps >= 1 and fps <= 75:
                    break
                else:
                    print("FPS is out of suggested range, please try again")
                    continue
            except ValueError:
                print("Invalid FPS. Please try a number")
            continue

        camera.Init()

        if not configure_continuous_acquisition(camera):
            return

        camera.BeginAcquisition()
        print("Recording started. Press 'q' in the image window to stop.")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(video_save, f"bottom_camera_{timestamp}.avi")

        while True:
            image_result = camera.GetNextImage(1000)

            if image_result.IsIncomplete():
                print(
                    "Image incomplete with image status "
                    f"{image_result.GetImageStatus()}"
                )
                image_result.Release()
                continue

            frame = convert_image_to_bgr(image_result)
            image_result.Release()

            if video_writer is None:
                height, width = frame.shape[:2]
                fourcc = cv2.VideoWriter.fourcc(*"XVID")
                video_writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))

            video_writer.write(frame)
            cv2.imshow("FLIR Grasshopper 3 Bottom - Recording", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        camera.EndAcquisition()

        if video_writer is not None:
            video_writer.release()

        cv2.destroyAllWindows()
        print(f"Video saved: {filename}")

    except Exception as e:
        print(f"Video recording error: {e}")

    finally:
        try:
            if camera.IsStreaming():
                camera.EndAcquisition()
        except Exception:
            pass

        if video_writer is not None:
            video_writer.release()

        cv2.destroyAllWindows()
        release_camera(system, cam_list, camera)


def camera_settings_menu(device_type, conn_settings):
    """Menu for reading and changing camera exposure and gain."""

    while True:
        print("\nBottom Camera Settings Menu\n")

        options = {
            "1": "Show Current Exposure/Gain",
            "2": "Set Exposure",
            "3": "Set Gain",
            "4": "Return",
        }

        for number, option in options.items():
            print(f"{number}: {option}")

        selection = input(
            "\nPlease select an option from the list above by selecting a number: "
        )

        if selection not in options:
            print(
                f"'{selection}' is an invalid selection: please select another option "
                "from the list above"
            )
            continue

        elif selection == "4":
            break

        elif selection == "1":
            show_current_settings(device_type, conn_settings)

        elif selection == "2":
            set_exposure(device_type, conn_settings)

        elif selection == "3":
            set_gain(device_type, conn_settings)


def show_current_settings(device_type, conn_settings):
    """Shows current exposure and gain settings."""

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return

    try:
        camera.Init()
        node_map = camera.GetNodeMap()

        exposure = PySpin.CFloatPtr(node_map.GetNode("ExposureTime"))
        gain = PySpin.CFloatPtr(node_map.GetNode("Gain"))

        exposure_value = (
            exposure.GetValue() if PySpin.IsReadable(exposure) else "Unavailable"
        )
        gain_value = gain.GetValue() if PySpin.IsReadable(gain) else "Unavailable"

        print(f"\nExposure Time: {exposure_value} μs")
        print(f"Gain: {gain_value} dB\n")

    except Exception as e:
        print(f"Could not read settings: {e}")

    finally:
        release_camera(system, cam_list, camera)


def set_exposure(device_type, conn_settings):
    """Sets manual exposure time in microseconds."""

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return

    try:
        raw_exposure = input("Please choose an exposure time (100-100000μs): ")

        exposure_value = float(raw_exposure)

        camera.Init()
        node_map = camera.GetNodeMap()

        exposure_auto = PySpin.CEnumerationPtr(node_map.GetNode("ExposureAuto"))
        if PySpin.IsWritable(exposure_auto):
            exposure_auto_off = exposure_auto.GetEntryByName("Off")
            exposure_auto.SetIntValue(exposure_auto_off.GetValue())

        exposure = PySpin.CFloatPtr(node_map.GetNode("ExposureTime"))

        if not PySpin.IsWritable(exposure):
            print("Exposure time is not writable")
            return

        min_exposure = exposure.GetMin()
        max_exposure = exposure.GetMax()

        if exposure_value < min_exposure or exposure_value > max_exposure:
            print(f"Exposure must be between {min_exposure} and {max_exposure} us")
            return

        exposure.SetValue(exposure_value)
        print(f"Exposure set to {exposure_value} us")

    except ValueError:
        print("Invalid exposure value")

    except Exception as e:
        print(f"Could not set exposure: {e}")

    finally:
        release_camera(system, cam_list, camera)


def set_gain(device_type, conn_settings):
    """Sets manual gain in dB."""

    system, cam_list, camera = get_camera(device_type, conn_settings)

    if camera is None:
        return

    try:
        raw_gain = input("Please choose a gain (0-24dB) : ")
        gain_value = float(raw_gain)

        camera.Init()
        node_map = camera.GetNodeMap()

        gain_auto = PySpin.CEnumerationPtr(node_map.GetNode("GainAuto"))
        if PySpin.IsWritable(gain_auto):
            gain_auto_off = gain_auto.GetEntryByName("Off")
            gain_auto.SetIntValue(gain_auto_off.GetValue())

        gain = PySpin.CFloatPtr(node_map.GetNode("Gain"))

        if not PySpin.IsWritable(gain):
            print("Gain is not writable")
            return

        min_gain = 0  # gain.GetMin()
        max_gain = 24  # gain.GetMax()

        if gain_value < min_gain or gain_value > max_gain:
            print(f"Gain must be between {min_gain} and {max_gain} dB")
            return

        gain.SetValue(gain_value)
        print(f"Gain set to {gain_value} dB")

    except ValueError:
        print("Invalid gain value")

    except Exception as e:
        print(f"Could not set gain: {e}")

    finally:
        release_camera(system, cam_list, camera)


def close_flir_system():
    global _flir_system, _flir_cam_list

    try:
        if _flir_cam_list is not None:
            _flir_cam_list.Clear()
    except Exception as e:
        print(f"Could not clear FLIR camera list: {e}")

    _flir_cam_list = None

    try:
        if _flir_system is not None:
            _flir_system.ReleaseInstance()
    except Exception as e:
        print(f"Could not release FLIR system: {e}")

    _flir_system = None
