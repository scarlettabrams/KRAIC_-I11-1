from KRAIC_I11_1.camera.helper.helper import (
    list_dict,
)

from .equipment.cam_focus_and_lights import (
    focus_and_light_commands,
)
from .equipment.cam_motion import (
    main_motion_commands,
)
from .equipment.cam_vision import (
    flir_grasshopper_3_commands,
)
from .equipment.el_flow_mfc import (
    bronkhorst_mfc_commands,
)
from .equipment.excelog6 import (
    data_logger_commands,
)
from .equipment.heating_PXU import (
    heating_pxu_commands,
)
from .equipment.julabo import (
    julabo_commands,
)
from .equipment.KDS_270 import (
    kds_270_commands,
)
from .equipment.reglo_z import (
    gear_pump_commands,
)
from .equipment.SF_10 import (
    sf_10_commands,
)


def equipment_menu(
    assigned_equipment,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
    image_save,
    video_save,
):
    """Equipment menu once equoipment has been confirmed"""

    while True:
        list_dict("Equipment Menu", assigned_equipment)

        selection = input(
            "\nPlease select a piece of equipment you want to control by typing a "
            "number: "
        )
        try:
            selection = int(selection)
        except ValueError:
            print("Invalid selection, please type an numerical integer from the list")
            continue

        if selection not in assigned_equipment:
            print(f"'{selection}' is an invalid selection, please try again")
            continue

        else:
            equipment = assigned_equipment.get(selection)

        # ------------------------------------------------------------------------------

        # The Fundamental pieces of equipment

        # ------------------------------------------------------------------------------

        if (
            equipment == "SF-10_Peristaltic_1"
            or equipment == "SF-10_Peristaltic_2"
            or equipment == "SF-10_Peristaltic_3"
        ):
            sf_10_commands(equipment, conn_settings, equipment_initialisation)
            continue

        elif equipment == "KDS_Syringe_Pump":
            kds_270_commands(equipment, conn_settings, equipment_initialisation)
            continue

        elif equipment == "Bronkhorst_MFC":
            bronkhorst_mfc_commands(equipment, conn_settings, equipment_initialisation)
            continue

        # ------------------------------------------------------------------------------

        # The KRAIC_Analysis pieces of equipment

        # ------------------------------------------------------------------------------

        elif equipment == "FLIR_Camera_Plane" or equipment == "FLIR_Camera_Top":
            flir_grasshopper_3_commands(
                equipment,
                conn_settings,
                equipment_initialisation,
                image_save,
                video_save,
            )
            continue

        elif equipment == "Focus_and_Lights":
            focus_and_light_commands(equipment, conn_settings, equipment_initialisation)
            continue

        elif equipment == "KRAIC-Analysis":
            main_motion_commands(equipment, conn_settings, equipment_initialisation)
            continue

        # ------------------------------------------------------------------------------

        # The KRAIC_G pieces of equipment

        # ------------------------------------------------------------------------------

        elif equipment == "Gear_Pump":
            gear_pump_commands(
                equipment, conn_settings, equipment_initialisation, gear_pump_path
            )
            continue

        elif equipment == "Heating_PXU":
            heating_pxu_commands(equipment, conn_settings, equipment_initialisation)
            continue

        elif equipment == "Excelog_6":
            data_logger_commands(equipment, conn_settings, equipment_initialisation)
            continue

        elif equipment == "JulaboFC600":
            julabo_commands(equipment, conn_settings, equipment_initialisation)
            continue

        # ------------------------------------------------------------------------------

        # Other

        # ------------------------------------------------------------------------------

        elif equipment == "Return to Main Menu":
            break

        else:
            print("Returning to equipment main menu")
            break
