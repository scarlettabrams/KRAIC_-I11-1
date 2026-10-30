import serial
import serial.tools.list_ports

from KRAIC_I11_1.camera.helper.helper import (
    load_json,
    update_json,
)


def comassign(equipments_list, conn_settings, equipment_initialisation):
    """assign equipment to the correct COM Port"""

    unassigned_equipments = []
    assigned_equipments = []

    connection = load_json(conn_settings)
    equipment = load_json(equipment_initialisation)

    for name in equipments_list.values():
        equipment[name]["COM_Assigned"] = False
        connection["CONNECTION_SETTINGS"][name]["port"] = False

        config = connection["CONNECTION_SETTINGS"].get(name)
        if not config:
            raise ValueError(f"No connection settings found for device type:{name}.")

        identifier = config.get("serial_number", None)

        if identifier is None:  # we don't put = None
            print(
                f"'No Serial Number identifier for {name} in connection_settings.json'"
            )

        else:
            ports = serial.tools.list_ports.comports()

            if not ports:
                continue

            for port in ports:
                if (
                    port.serial_number and port.serial_number.strip() == identifier
                ):  # we check it exists first and then strip it if it does
                    com_port = port.device.strip()
                    equipment[name]["COM_Assigned"] = True
                    connection["CONNECTION_SETTINGS"][name]["port"] = com_port
                    break

                else:
                    continue

    connection = update_json(conn_settings, connection)
    equipment = update_json(equipment_initialisation, equipment)

    for name in equipments_list.values():
        port_value = connection["CONNECTION_SETTINGS"][name].get("port")
        if port_value:
            assigned_equipments.append(name)
        else:
            unassigned_equipments.append(name)
            continue

    return assigned_equipments, unassigned_equipments


def print_comassign(assigned_equipments, unassigned_equipments):
    """let the user know the equipment that is being assigned and what is not"""

    print("\nCOM ports assigned to the following equipment \n")

    for assigned_equipment in assigned_equipments:
        print(f"\t\t- {assigned_equipment}")

    print("\nThe following equipment have not been assigned a COM port")
    print(
        "Remote control of these devices will be disabled if you choose to proceed\n\n"
    )

    for unassigned_equipment in unassigned_equipments:
        print(f"\t\t- {unassigned_equipment}")
