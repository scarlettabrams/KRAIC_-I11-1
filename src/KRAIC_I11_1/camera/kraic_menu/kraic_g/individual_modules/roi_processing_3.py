import os
import shutil

from KRAIC_I11_1.camera.helper.helper import (
    load_json,
    press_enter,
    update_json,
)

from .backend.roi_identification_vertical_line_1 import (
    interactive_roi_selection,
)

# put somehting in here to get to the ROI selection


def do_roi_processing(folder_name, folder_path, flir_device_path, cal_progress):
    """Once an image has been taken of the KRAIC-G we need to get give the ROI
    coordinates
    """

    print("\n\nROI PROCESSING")
    print("\t-Ensure the FLIR E5 is connected")
    print(
        "\t-Ensure the FLIR-E5 is fixed in a position that will not change over the "
        "course of this calibration"
    )
    print(
        "\t-Drag the ROI over the electrical tape with the top and bottom of the "
        "region enclosed by the top and bottom tube"
    )

    flag = press_enter(
        "Press ENTER when the FLIR is connected and ready to extract images, or 'e' to "
        "exit'to calibration workflow."
    )

    if flag:
        # picture moving and file
        # sorting-----------------------------------------------------------------------

        dest_root = os.path.join(folder_path, "ROI_Detection_Image")
        os.makedirs(dest_root, exist_ok=True)

        # Copy all folders from FLIR into a subfolder per source to avoid collisions

        try:
            for entry in os.listdir(flir_device_path):
                src = os.path.join(flir_device_path, entry)
                if not os.path.isdir(src):
                    continue
                dest_sub = os.path.join(dest_root, entry)
                try:
                    shutil.copytree(src, dest_sub, dirs_exist_ok=True)
                    # Optionally remove from device — keep original behaviour but
                    # swallow errors
                    try:
                        shutil.rmtree(src)
                    except Exception:
                        # If removal fails, ignore to avoid destructive behaviour
                        # causing crashes.
                        pass
                except Exception as e:
                    print(f"Warning: failed to copy/remove {src}: {e}")
                    return

        except Exception:
            print(f"Warning: failed to find FLIR-E5 directory: {flir_device_path}")
            return

        # Collect image paths
        img_path = []
        for root, _, files in os.walk(dest_root):
            for f in sorted(files):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".tiff", ".bmp")):
                    img_path.append(os.path.join(root, f))

        if not img_path:
            print("No images for ROI processing — abort.")
            return

        # ROI
        # selection---------------------------------------------------------------------

        # Run interactive ROI/trough detection
        coordinate_dict = interactive_roi_selection(img_path)

        # Save detected coordinates (ensure serializable)
        progress = load_json(cal_progress)

        progress["CALIBRATION_STATUS"][folder_name]["ROI_Image_Processed"] = True
        progress["CALIBRATION_STATUS"][folder_name]["Coordinates"] = coordinate_dict

        progress = update_json(cal_progress, progress)

        print("\n\nROI Processing complete.")
