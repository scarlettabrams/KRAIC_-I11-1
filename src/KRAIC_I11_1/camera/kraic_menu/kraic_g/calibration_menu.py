import os
import time

from KRAIC_I11_1.camera.helper.helper import (
    list_dict,
    load_json,
)
from KRAIC_I11_1.camera.kraic_menu.kraic_g.cal_driver import (
    new_entry,
    resume_calibration,
)


def cal_menu(
    cal_root_folder,
    flir_device_path,
    cal_progress,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
):
    """Allows the user to select a complete calibration, continue with a partially
    completed one or begin a new one
    """

    while True:
        calibration = load_json(cal_progress)

        cal_folders = []

        for item in os.listdir(cal_root_folder):
            cal_folders.append(item)

        end_tags = ["Begin New Calibration", "Return to KRAIC Menu"]

        user_options = cal_folders + end_tags

        i = 1
        keys = []
        while i <= len(user_options):
            keys.append(str(i))
            i = i + 1

        user_dict = dict(zip(keys, user_options, strict=False))

        list_dict("Calibration Options", user_dict)

        selection = input(
            "\nPlease choose a calibration option by selecting a number from the list "
            "above: "
        )

        if selection == str(len(user_options) - 1):
            new_entry(
                cal_root_folder,
                flir_device_path,
                cal_progress,
                conn_settings,
                equipment_initialisation,
                gear_pump_path,
            )

        elif selection == str(len(user_options)):
            print("\nReturning to KRAIC Menu")
            break

        elif selection in user_dict:
            folder_name = user_dict[selection]
            folder_path = os.path.join(cal_root_folder, folder_name)
            changing = folder_name.replace("Folder", "")
            wb_name = changing + "Workbook.xlsx"
            wb_path = f"{folder_path}/{wb_name}"

            completed = calibration["CALIBRATION_STATUS"][folder_name]["Completed"]

            if completed:
                print(
                    "You have selected a completed calibration!\n\nThis calibrations "
                    "fingerprint can be seen below:"
                )

                # we want to check the excel first page for the
                # fingerprint---------------------------------------------fingerprint.py
                # (new)
                selection2 = input(
                    "Would you like to proceed to selecting heating gradient(y/n)? "
                )

                if selection2.lower() == "y":
                    # create the module and place it in
                    # here------------------------------------------choose_conditions.py
                    # (new)
                    print("hello")

                elif selection2.lower() == "n":
                    print("Returning to calibration menu")
                    time.sleep(3)
                    continue

                else:
                    print(
                        f"'{selection2}' is an invalid selection, please try selecting "
                        "a calibration option again"
                    )
                    continue

            else:
                print(
                    "You have selected an incomplete calibration!\n\nThis calibrations "
                    "fingerprint can be seen below:"
                )

                # we want to check the excel first paget for the fingerprint
                # --------------------------------------------------------fingerprint.py
                # (new)

                selection3 = input(
                    "Would you like to continue with this calibration(y/n)? "
                )

                if selection3.lower() == "y":
                    resume_calibration(
                        folder_name,
                        folder_path,
                        wb_path,
                        cal_progress,
                        flir_device_path,
                        conn_settings,
                        equipment_initialisation,
                        gear_pump_path,
                    )

                elif selection3.lower() == "n":
                    print("Returning to calibration menu")
                    time.sleep(3)
                    continue

                else:
                    print(
                        f"'{selection3}' is an invalid selection, please try selecting "
                        "a calibration option again"
                    )
                    continue

        else:
            print(f"'{selection}' is an invalid selection, please try again")
            continue
