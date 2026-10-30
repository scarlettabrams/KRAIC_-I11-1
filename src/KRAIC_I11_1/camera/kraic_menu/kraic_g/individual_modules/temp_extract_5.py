from KRAIC_I11_1.camera.helper.helper import (
    load_json,
    press_enter,
    update_json,
)

from .backend.image_analysis_4 import (
    main,
)


def do_calibration_image_processing(
    folder_name, folder_path, wb_path, cal_progress, flir_device_path
):

    progress = load_json(cal_progress)

    coordinates = progress["CALIBRATION_STATUS"][folder_name].get(
        "Coordinates"
    )  # the line coordinates specified
    orientation = progress["CALIBRATION_STATUS"][folder_name].get(
        "Orientation"
    )  # does solution move up or down

    print("\nCalibration image analysis...\n")

    press_enter("Plug in FLIR and press ENTER to begin extraction or 'e' to exit'.")

    result, flag = main(
        flir_device_path,
        folder_path,
        coordinates,
        wb_path,
        cal_progress,
        folder_name,
        orientation,
    )

    print(f"\n\n{result}")

    if flag:
        progress = load_json(cal_progress)
        coordinates = progress["CALIBRATION_STATUS"][folder_name][
            "Calibration_Images_Processed"
        ] = True
        update_json(cal_progress, progress)

    else:
        print(
            "Please check connections and locations of images before beginning the "
            "next image processing attempt"
        )
