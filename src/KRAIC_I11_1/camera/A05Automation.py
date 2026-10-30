import time

from KRAIC_I11_1.camera.com_assignment.com_auto_assign import comassign, print_comassign
from KRAIC_I11_1.camera.helper.helper import (
    clear_screen,
    list_dict,
    load_json,
    passwd,
)
from KRAIC_I11_1.camera.imaging.imaging import img_menu
from KRAIC_I11_1.camera.individual_equipment_control_menu.equipment_menu import (
    equipment_menu,
)
from KRAIC_I11_1.camera.kraic_menu.the_kraics import kraic_options

# --------------------------------------------------------------------------------------

### HAVE YOU GOT ALL THE NECESSARY JSONs IN PLACE

# --------------------------------------------------------------------------------------


# Main Script
# path to the protected password information
user_info = "/home/enybh/Lab_Control/lab_automation/json/.user_info.json"
# path to the equipment serial connections
conn_settings = "/home/enybh/Lab_Control/lab_automation/json/connection_settings.json"
# the equipment that is being used currently
equipment_initialisation = (
    "/home/enybh/Lab_Control/lab_automation/json/equip_initialisation.json"
)

# KRAIC-G calibration
# where the calibration excel document will be placed
cal_root_folder = "/home/enybh/Lab_Control/lab_automation/calibrations"
FLIR_DEVICE_PATH = (
    "/media/enybh/FLIR E5/DCIM/"  # location where the FLIR E5 is found when plugged in
)
# json where cal progress is tracked
cal_progress = "/home/enybh/Lab_Control/lab_automation/json/calibration.json"


# REGLO Z Gear Pump
gear_pump_path = "/home/enybh/Lab_Control/lab_automation/json/asynt.json"


# Camera Vision tests
image_save_test = "/media/enybh/Pea Expansion/Test_Folder/Images"
video_save_test = "/media/enybh/Pea Expansion/Test_Folder/Vids"

# Real Vision Files
video_save = "/media/enybh/Pea Expansion/Imaging_Folder"
img_settings = "/home/enybh/Lab_Control/lab_automation/json/img_settings.json"


# --------------------------------------------------------------------------------------

### LIST OF POSSIBLE EQUIPMENT

# --------------------------------------------------------------------------------------

equipments_list = {
    "1": "SF-10_Peristaltic_1",  # Alwyas used
    "2": "SF-10_Peristaltic_2",  # Always used
    "3": "SF-10_Peristaltic_3",  # Always used
    "4": "KDS_Syringe_Pump",  # Always used
    "5": "Bronkhorst_MFC",  # Always used
    "6": "Focus_and_Lights",  # KRAIC-Analysis
    "7": "KRAIC-Analysis",  # KRAIC-Analysis
    "8": "Gear_Pump",  # KRAIC-G
    "9": "Heating_PXU",  # KRAIC-G
    "10": "Excelog_6",  # KRAIC-G
    "11": "JulaboFC600",  # KRAIC-G
}


# --------------------------------------------------------------------------------------

### PASSWORD CHECK

# --------------------------------------------------------------------------------------

passwd(user_info)


# --------------------------------------------------------------------------------------

### EQUIPMENT LIST

# --------------------------------------------------------------------------------------

list_dict("Equipment List", equipments_list)


# --------------------------------------------------------------------------------------

### HARDWARE CONNECTION CHECK, COM ASSIGNMENT

# --------------------------------------------------------------------------------------

assigned_equipments_list, unassigned_equipments_list = comassign(
    equipments_list, conn_settings, equipment_initialisation
)

print_comassign(assigned_equipments_list, unassigned_equipments_list)


# --------------------------------------------------------------------------------------

### Main Menu

# --------------------------------------------------------------------------------------


while True:
    time.sleep(2)

    clear_screen(40)

    assigned_equipments_list, unassigned_equipments_list = comassign(
        equipments_list, conn_settings, equipment_initialisation
    )

    assigned_equipments_dict = {}

    if assigned_equipments_list:
        connection = load_json(conn_settings)
        i = 1

        for name in equipments_list.values():
            port_value = connection["CONNECTION_SETTINGS"][name].get("port")

            if port_value:
                assigned_equipments_dict[i] = name
                i = i + 1
            else:
                continue
        FLIR_Camera_Top = len(assigned_equipments_list) + 1

        assigned_equipments_dict[FLIR_Camera_Top] = "FLIR_Camera_Top"

        FLIR_Camera_Plane = len(assigned_equipments_list) + 2

        assigned_equipments_dict[FLIR_Camera_Plane] = "FLIR_Camera_Plane"

        rtm = len(assigned_equipments_list) + 3

        assigned_equipments_dict[rtm] = "Return to Main Menu"

    main_menu = {
        "1": "Individual Equipment Control",
        "2": "KRAIC",
        "3": "Inline Imaging",
        "4": "COM Assignment",
        "5": "Quit",
    }

    list_dict("Main Menu", main_menu)
    selection = input(
        "\nPlease choose one of the above options by selecting a number: "
    )

    if selection == "1":
        if assigned_equipments_list:
            equipment_menu(
                assigned_equipments_dict,
                conn_settings,
                equipment_initialisation,
                gear_pump_path,
                image_save_test,
                video_save_test,
            )

        else:
            print(
                "\nThere are no pieces of equipment assigned, please connect equipment "
                "and try again!"
            )
            continue

    elif selection == "2":
        kraic_options(
            assigned_equipments_list,
            cal_root_folder,
            FLIR_DEVICE_PATH,
            cal_progress,
            conn_settings,
            equipment_initialisation,
            gear_pump_path,
        )

    elif selection == "3":
        if (
            "FLIR_Camera_Top" in assigned_equipments_dict.values()
            and "FLIR_Camera_Plane" in assigned_equipments_dict.values()
            and "Focus_and_Lights" in assigned_equipments_dict.values()
            and "KRAIC-Analysis" in assigned_equipments_dict.values()
        ):
            time.sleep(1.5)
            print("All the necessary equipment available!")

            img_menu(video_save, conn_settings, img_settings)

        else:
            print("\nPlease ensure all the equipment is connected")
            continue

    elif selection == "4":
        print_comassign(assigned_equipments_list, unassigned_equipments_list)

    elif selection == "5":
        print("Exiting the script")
        time.sleep(2)
        exit()

    else:
        print(f"'{selection}' is an invalid selection, please try again")
        continue
