import os

from KRAIC_I11_1.camera.helper.helper import (
    load_json,
    press_enter,
    update_json,
)

from .backend.image_analysis_4 import (
    main as image_analysis_main,
)


def do_calibration_image_processing(
    folder_name, folder_path, wb_path, cal_progress, flir_device_path
):

    progress = load_json(cal_progress)

    coordinates = progress["CALIBRATION_STATUS"][folder_name].get("Coordinates")
    orientation = progress["CALIBRATION_STATUS"][folder_name].get("Orientation")

    print("\nCalibration image analysis...\n")

    flag = press_enter(
        "Plug in FLIR and press ENTER to begin extraction or 'e' to exit'."
    )

    if not flag:
        return

    image_save_folder = os.path.join(folder_path, "Calibration_Images")

    result, flag = image_analysis_main(
        flir_device_path,
        image_save_folder,
        coordinates,
        wb_path,
        cal_progress,
        folder_name,
        orientation,
    )

    if flag:
        progress = load_json(cal_progress)
        coordinates = progress["CALIBRATION_STATUS"][folder_name][
            "Calibration_Images_Processed"
        ] = True
        update_json(cal_progress, progress)

    print(f"\n\n{result}")

    if not flag:
        print(
            "Please check connections and locations of images before beginning the "
            "next image processing attempt"
        )
