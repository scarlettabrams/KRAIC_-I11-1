import os
import time
from datetime import datetime

from openpyxl import Workbook

from KRAIC_I11_1.camera.helper.helper import (
    clear_screen,
    load_json,
    update_json,
)

from .individual_modules.calibration_program_4 import (
    run_calibration_program,
)
from .individual_modules.roi_identification_2 import (
    do_roi_identification,
)
from .individual_modules.roi_processing_3 import (
    do_roi_processing,
)
from .individual_modules.temp_extract_6 import (
    do_calibration_image_processing,
)
from .individual_modules.workbook_prep_1 import (
    prepare_calibration_workbook,
)

# ======================================================================================


def create_matrix():
    """if we select to make a new calibration folder this is the route to take"""

    print(
        "Please begin by maiking an experimental matrix by answering the following "
        "questions"
    )
    time.sleep(2)

    while True:
        clear_screen(5)

        # hot experimental space -------------------------------------------------------

        print(
            "\n\nSelect the maximum and minimum superambient setpoints(30-60℃ ), "
            "alongside the increments you would like to pursue at the heated extremity "
            "(solution inlet) of the KRAIC-G"
        )
        hot1 = input("Please input the minimum temperature(℃ ): ")
        hot2 = input("Please input the maximum temperature(℃ ): ")
        hot3 = input(
            "Please input the number (integer) of temperatures beween the min and max "
            "temperature (℃ ): "
        )

        try:
            hot1_float = abs(round(float(hot1), 1))
            hot2_float = abs(round(float(hot2), 1))
            hot3_float = abs(round(float(hot3), 0)) + 1

        except Exception as e:
            print(f"Error Message:{e}")
            print("\n\nTry this section again")
            continue

        if (
            hot1_float >= 30
            and hot1_float <= 60
            and hot2_float > hot1_float
            and hot2_float <= 60
            and hot3_float <= 15
        ):
            break

        else:
            print(
                "Temperatures or increments are outside of given range, please try "
                "again"
            )
            continue

    # cold experimental space -------------------------------------------------------

    while True:
        clear_screen(5)

        print(
            "\n\nSelect the maximum and minimum subambient setpoints(5-20℃ ), "
            "alongside the increments you would like to pursue at the cooled extremity "
            "(solution outlet) of the KRAIC-G"
        )
        cold1 = input("Please input the minimum temperature(℃ ): ")
        cold2 = input("Please input the maximum temperature(℃ ): ")
        cold3 = input(
            "Please input the number (integer) of temperatures beween the min and max "
            "temperature (℃ ): "
        )

        try:
            cold1_float = abs(round(float(cold1), 1))
            cold2_float = abs(round(float(cold2), 1))
            cold3_float = abs(round(float(cold3), 0)) + 1

        except Exception as e:
            print(f"Error Message:{e}")
            print("\n\nTry this section again")
            continue

        if (
            cold1_float >= 5
            and cold1_float <= 20
            and cold2_float > cold1_float
            and cold2_float <= 20
            and cold3_float <= 15
        ):
            break

        else:
            print(
                "Temperatures or increments are outside of given range, please try "
                "again"
            )
            continue

    # flow experimental space -------------------------------------------------------

    while True:
        clear_screen(5)

        print(
            "\n\nSelect the maximum and minimum flowrate setpoints(0-114ml/min), "
            "alongside the increments you would like to pursue for coolant flowrate "
            "entering the KRAIC-G"
        )
        print(
            "The system will get as close to the user setpoints as possible, however "
            "equipment limitations require flowrate conditions to be adjusted so they "
            "are divisible by 1.9ml/min"
        )
        flow1 = input("Please input the minimum flowrate(ml/min): ")
        flow2 = input("Please input the maximum flowrate(ml/min): ")
        flow3 = input(
            "Please input the number (integer) of increments between the min and max "
            "flowrate (ml/min): "
        )

        try:
            flow1_float = abs(round(float(flow1), 1))
            flow2_float = abs(round(float(flow2), 1))
            flow3_float = abs(round(float(flow3), 0)) + 1

        except Exception as e:
            print(f"Error Message:{e}")
            print("\n\nTry this section again")
            continue

        if (
            flow1_float >= 0
            and flow1_float <= 114
            and flow2_float > flow1_float
            and flow2_float <= 114
            and flow3_float <= 30
        ):
            break

        else:
            print(
                "Temperatures or increments are outside of given range, please try "
                "again"
            )
            continue

    # hot temperatures list -------------------------------------------------------

    clear_screen(10)

    add_hot = (hot2_float - hot1_float) / (hot3_float)

    print("\n\nHot temperatures(℃ )")
    hot_list = []
    while round(hot1_float, 1) <= hot2_float:
        round_hot = round(hot1_float, 1)
        hot_list.append(round_hot)
        print(f"{round_hot}")
        hot1_float = hot1_float + add_hot

    # cold temperatures list -------------------------------------------------------

    add_cold = (cold2_float - cold1_float) / (cold3_float)

    print("\n\nCold temperatures(℃ )")
    cold_list = []
    while round(cold1_float, 1) <= cold2_float:
        round_cold = round(cold1_float, 1)
        cold_list.append(round_cold)
        print(f"{round_cold}")
        cold1_float = cold1_float + add_cold

    # flow rate list ---------------------------------------------------------------

    add_flow = (flow2_float - flow1_float) / (flow3_float)

    print("\n\nCoolant Flowrates(ml/min)")
    flow_list = []
    while round(flow1_float, 1) <= flow2_float:
        round_flow = round(flow1_float, 1)
        flow_list.append(round_flow)
        print(f"{round_flow}")
        flow1_float = flow1_float + add_flow

    # Max no. of experiments --------------------------------------------------------

    total_no = len(hot_list) * len(cold_list) * len(flow_list)

    print(f"\n\nThere will be a maximum of {total_no} experiments")

    # Final Confirmation-------------------------------------------------------------

    while True:
        confirmation = input(
            "\n\nWould you like to use these values to create your experimental mesh "
            "and begin a new eperiment (y/n)"
        )

        if confirmation == "y":
            print("\n\nProceeding to the next section.")
            return hot_list, cold_list, flow_list
            break

        elif confirmation == "n":
            print("\n\nReturning to calibration menu.")
            return False, False, False
            break

        else:
            print(f"\n\n'{confirmation}' is an invalid selection, please try again")
            continue


# ======================================================================================


def create_calibration(cal_root_folder, cal_progress, hot_list, cold_list, flow_list):
    """begin creating the filee structure and the json progress file"""

    progress = load_json(cal_progress)

    now = datetime.now()
    stamp = f"{now.day}_{now.month}_{now.year}_{now.hour}_{now.minute}"
    folder_name = f"{stamp}_Calibration_Folder"
    folder_path = os.path.join(cal_root_folder, folder_name)

    os.makedirs(folder_path, exist_ok=True)

    wb_name = f"{stamp}_Calibration_Workbook.xlsx"
    wb_path = os.path.join(folder_path, wb_name)

    wb = Workbook()
    ws = wb.worksheets[0]
    ws.title = "Calibration Description"
    wb.save(wb_path)

    if "CALIBRATION_STATUS" not in progress:
        progress["CALIBRATION_STATUS"] = {}

    temp_commands = {}

    for temperature in hot_list:
        ten_temperature = temperature * 10
        temp_commands[ten_temperature] = cold_list

    if folder_name not in progress["CALIBRATION_STATUS"]:
        progress["CALIBRATION_STATUS"][folder_name] = {
            "ROI_Identification_Image": False,
            "ROI_Image_Processed": False,
            "Coordinates": False,
            "Orientation": False,
            "Preparation": False,
            "Calibration": {
                "Status": False,
                "Temperature_commands": temp_commands,
                "Flow_commands": flow_list,
                "Current_flow": flow_list[0],
                "Experiment": 0,
            },
            "Calibration_Images_Processed": False,
            "Completed": False,
        }

    progress = update_json(cal_progress, progress)

    return folder_name, folder_path, wb_path


# ======================================================================================
def resume_calibration(
    folder_name,
    folder_path,
    wb_path,
    cal_progress,
    flir_device_path,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
):
    """when a calibration can be seen that it is not complete we enter this workflow"""

    while True:
        progress = load_json(cal_progress)

        state = progress["CALIBRATION_STATUS"][folder_name]

        response = (
            input(
                "\n\nPlease click ENTER to continue to next step or 'e' to exit "
                "calibration "
            )
            .strip()
            .lower()
        )

        if response == "e":
            print("\n\nExiting program to Calibration Menu")
            break  # exit the loop

        elif response == "":
            # Step1=====================================================================

            if not state.get("ROI_Identification_Image", False):
                do_roi_identification(folder_name, cal_progress)
                continue

            # Step2=====================================================================

            if not state.get("ROI_Image_Processed", False):
                do_roi_processing(
                    folder_name, folder_path, flir_device_path, cal_progress
                )
                continue

            # Step3=====================================================================

            if not state.get("Preparation", False):
                prepare_calibration_workbook(folder_name, wb_path, cal_progress)
                continue

            # Step4=====================================================================

            if not state.get("Calibration", {}).get("Status", False):
                print(f"{wb_path}")  ###############################
                run_calibration_program(
                    folder_name,
                    wb_path,
                    cal_progress,
                    conn_settings,
                    equipment_initialisation,
                    gear_pump_path,
                )
                continue

            # Step5=====================================================================

            if not state.get("Calibration_Images_Processed", False):
                do_calibration_image_processing(
                    folder_name, folder_path, wb_path, cal_progress, flir_device_path
                )
                continue

            # Step6=====================================================================

            state["Completed"] = True
            progress = update_json(cal_progress, progress)
            print("\nCalibration fully completed.\n")
            break

        else:
            print(f"'{response}' is an invalid selection, please try again")
            continue


# ======================================================================================


def new_entry(
    cal_root_folder,
    flir_device_path,
    cal_progress,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
):
    """The main entry point for new and incomplete calibration files"""

    hot_list, cold_list, flow_list = create_matrix()

    if hot_list and cold_list and flow_list:
        folder_name, folder_path, wb_path = create_calibration(
            cal_root_folder, cal_progress, hot_list, cold_list, flow_list
        )

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

        print("\n\nReturning to calibration menu")

        return

    else:
        return


# ======================================================================================
