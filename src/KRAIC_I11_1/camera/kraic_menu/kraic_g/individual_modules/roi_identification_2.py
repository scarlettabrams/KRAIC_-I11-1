from KRAIC_I11_1.camera.helper.helper import (
    load_json,
    press_enter,
    update_json,
)


def do_roi_identification(folder_name, cal_progress):

    progress = load_json(cal_progress)

    print("\n\nROI IDENTIFICATION")
    print(
        "\t-Ensure the FLIR E5 is in full view of the top and bottom tube on the "
        "KRAIC-G"
    )
    print("\t-Ensure the FLIR E5 is disconnected")
    print(
        "\t-Ensure the FLIR-E5 is fixed in a position that will not change over the "
        "course of this calibration"
    )
    print(
        "\t-Place a piece of electrical tape from the top tube to the bottom tube in "
        "the line of sight of the FLIR-E5"
    )

    flag = press_enter(
        "\nTake ROI identification image now. Press ENTER when finished, or 'e' to "
        "exit'to calibration workflow"
    )

    if flag:
        progress["CALIBRATION_STATUS"][folder_name]["ROI_Identification_Image"] = True

        progress = update_json(cal_progress, progress)
        print("\n\nROI image recorded - please leave the camera in the same position")
