from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import (
    load_json,
)


def julabo_commands(device_type, conn_settings, equipment_initialisation):
    """Defines all the possible commands you could need to run the julabo FC600"""
    print("Accessing remote control options ")

    connection = load_json(conn_settings)

    while True:
        print("\nJulabo FC600 Menu\n")

        options = {
            "1": "Test Command",
            "2": "Start Pump",
            "3": "Stop Pump",
            "4": "Set working Temperature",
            "5": "Current Status",
            "6": "Exit to Main Menu",
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

        elif selection == "6":
            print("Returning to Main Menu")
            break

        else:
            command = connection["COMMANDS"][device_type].get(selection)

        while True:
            if selection == "4":
                try:
                    raw_string = input("What temperature would you like (5-60°C): ")
                    raw_float = float(raw_string)

                except ValueError as e:
                    print(f"\n{e} - Please type a number in the given range\n")
                    continue

                new_float = round(raw_float, ndigits=1)

                print(f"\nTemperature being sent : {new_float}")

                if new_float < 5 or new_float > 60:
                    print("This number falls outside safety limits - please try again")
                    continue
                else:
                    new_string = str(new_float)
                    command = command + new_string

                    with PyConnection(device_type, conn_settings) as conn:
                        response = conn.send_serial(command)

                    print(f"Device response: {response}")

                    break

            elif selection == "5":
                for key, value in command.items():
                    with PyConnection(device_type, conn_settings) as conn:
                        response = conn.send_serial(value)
                        print(f"\n{key}: {response}\n")

                    break
                break

            else:
                with PyConnection(device_type, conn_settings) as conn:
                    response = conn.send_serial(command)

                print(f"Device response: {response}")
                break
