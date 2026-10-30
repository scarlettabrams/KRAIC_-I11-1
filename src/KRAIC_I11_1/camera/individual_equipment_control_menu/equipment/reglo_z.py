import time

from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import (
    load_json,
    update_json,
)


def gear_pump_commands(
    device_type, conn_settings, equipment_initialisation, gear_pump_path
):
    """Defines all the possible commands you could need to run the SF_10"""

    reglo_z = load_json(gear_pump_path)

    while True:
        print("\nREGLO Z Gear Pump Menu\n")

        options = {
            "1": "Current Setpoint",
            "2": "Send Flowrate",
            "3": "Exit to Main Menu",
        }

        for number, option in options.items():
            print(f"{number}: {option}")

        selection = input(
            "\nPlease select an option from the list above by selecting a number: "
        )

        if selection not in options:
            print(
                f"'{selection}' is an invalid selection: please select another option "
                "from the list above"
            )
            continue

        elif selection == "3":
            break

        if selection == "1":
            current_left = int(reglo_z["CURRENT_VALUE"]["Left"]) * 10
            current_right = int(reglo_z["CURRENT_VALUE"]["Right"])

            analogue_flowrate = current_left + current_right

            actual_flowrate = 1.9 * analogue_flowrate

            print(f"Current Flowrate: {actual_flowrate}ml/min")

        else:
            while True:
                flowrate_str = input(
                    "Please input a new flowrate between 0-114 ml/min: "
                )

                try:
                    flowrate_int = float(flowrate_str)

                    if flowrate_int < 0 or flowrate_int > 115:
                        print("Please input a flowrate within the given range")
                        time.sleep(2)
                        continue

                    else:
                        break

                except ValueError:
                    print("Invalid response - please try again")
                    continue

            command_setting(
                flowrate_int,
                conn_settings,
                equipment_initialisation,
                gear_pump_path,
                device_type,
            )


def command_setting(
    flowrate_int,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
    device_type="Gear_Pump",
    selection="2",
):

    connection = load_json(conn_settings)
    reglo_z = load_json(gear_pump_path)

    command2 = connection["COMMANDS"][device_type][selection]

    numbers = list(str(round((flowrate_int / 1.9), ndigits=0)))

    length = len(numbers)

    if length == 3:
        try:
            right = int(numbers[0])
            left = 0
        except ValueError:
            left = 0
            right = 0

    else:
        try:
            left = int(numbers[0])
        except ValueError:
            left = 0

        try:
            right = int(numbers[1])
        except ValueError:
            right = 0

    current_left = int(reglo_z["CURRENT_VALUE"]["Left"])
    current_right = int(reglo_z["CURRENT_VALUE"]["Right"])

    change_left = left - current_left
    change_right = right - current_right

    change_left_abs = abs(change_left)
    change_right_abs = abs(change_right)

    i = 1

    if change_left > 0:
        command_left = command2["left_up"]
    else:
        command_left = command2["left_down"]

    while i <= change_left_abs:
        with PyConnection(device_type, conn_settings) as conn:
            conn.send_serial(command_left[0])
            time.sleep(0.6)
            conn.send_serial(command_left[1])
            i = i + 1

    i = 1

    if change_right > 0:
        command_right = command2["right_up"]
    else:
        command_right = command2["right_down"]

    while i <= change_right_abs:
        with PyConnection(device_type, conn_settings) as conn:
            conn.send_serial(command_right[0])
            time.sleep(0.6)
            conn.send_serial(command_right[1])
            i = i + 1

    new_left = str(left)
    new_right = str(right)

    reglo_z["CURRENT_VALUE"]["Left"] = new_left
    reglo_z["CURRENT_VALUE"]["Right"] = new_right

    new_value_ana = new_left + new_right

    print(f"New Analogue Flow Setting:{new_value_ana}")

    new_value_flow = float(new_value_ana) * 1.9

    flowrate_set = round(new_value_flow, ndigits=1)

    print(f"New Flowrate Setting (ml/min): {flowrate_set}")

    reglo_z = update_json(gear_pump_path, reglo_z)
