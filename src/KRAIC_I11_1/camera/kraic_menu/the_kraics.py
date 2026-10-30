import time

from KRAIC_I11_1.camera.helper.helper import (
    clear_screen,
    list_dict,
)
from KRAIC_I11_1.camera.kraic_menu.kraic_g.calibration_menu import cal_menu

# update this for KRAIC-G calibration


def kraic_options(
    assigned_equipments_list,
    cal_root_folder,
    flir_device_path,
    cal_progress,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
):
    """Function displaying all the KRAICs currently available"""

    while True:
        clear_screen(30)

        kraic_dict = {
            "1": "KRAIC-S",
            "2": "KRAIC-T",
            "3": "KRAIC-G",
            "4": "Return to Main Menu",
        }

        list_dict("KRAIC Options", kraic_dict)

        selection = input(
            "\nPlease choose one of the above options by selecting a number: "
        )

        if selection == "1":
            time.sleep(2)
            print("\n\nNo prior setup is required for this option!")

            # we can move towards run_time

        elif selection == "2":
            time.sleep(2)
            print(
                "\n\nThe remote control module for this crystalliser is yet to be setup"
            )

        elif selection == "3":
            if (
                "Gear_Pump"
                and "Heating_PXU"
                and "Excelog_6"
                and "JulaboFC600" in assigned_equipments_list
            ):
                time.sleep(1)

                print(
                    "All necessary equipment is connected, proceeding to calibration "
                    "selection"
                )

                cal_menu(
                    cal_root_folder,
                    flir_device_path,
                    cal_progress,
                    conn_settings,
                    equipment_initialisation,
                    gear_pump_path,
                )

                # if a calibration has been selected with setpoints we can move towards
                # run_time, flag indicates

            else:
                print(
                    "Supporting equipment unavailable, check connection for: \n\t - "
                    "Gear_Pump \n\t - Heating_PXU \n\t - Excelog_6 \n\t - JulaboFC600 "
                )
                print("\nReturning to KRAIC menu")

                time.sleep(2)
                continue

        elif selection == "4":
            print("Returning to main menu")

            time.sleep(3)
            break

        else:
            print(f"'{selection}' is an invalid selection, please try again")
