import time

from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import (
    list_dict,
    load_json,
    update_json,
)


def kds_270_commands(device_type, conn_settings, equipment_initialisation):
    """Defines all the possible commands you could need to run the KDS_270 syringe
    pump
    """

    connection = load_json(conn_settings)

    while True:
        connection = update_json(conn_settings, connection)

        print("\nKDS 270 Continuous Syringe Pump Menu\n")

        options = {
            "1": "Test Command",
            "2": "Mode and Settings",
            "3": "Start Pump",
            "4": "Stop Pump",
            "5": "Return to Main Menu",
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

        if selection == "5":
            break

        if selection == "2":
            mode = {"1": "Fill Pump", "2": "Empty Pump"}

            while True:
                list_dict("mode menu", mode)

                commands = connection["COMMANDS"][device_type].get(selection)
                mode_commands = connection["COMMANDS"][device_type].get("3")

                mode_selection = input(
                    "\nPlease select an option from the list above: "
                )

                if mode_selection in mode:
                    cont = commands[mode_selection].get("cycle")
                    direction = commands[mode_selection].get("start_command")
                    rate = commands[mode_selection].get("flow_command")

                    if direction == "irun":
                        stripped_rate = (rate.replace("irate", "")).strip()

                    else:
                        stripped_rate = (rate.replace("wrate", "")).strip()

                    print(f"Current flow in mode selected: {stripped_rate}")

                    response = input(
                        "Would you like to adjust the above flowrate? (y/n) "
                    ).strip()

                    if response == "n":
                        print("\nSetting Confirmed!\n")

                        mode_commands["Mode"] = cont
                        mode_commands["Start"] = direction
                        mode_commands["Rate"] = rate

                        update_json(conn_settings, connection)
                        break

                    elif response == "y":
                        while True:
                            try:
                                raw_rate_float = float(
                                    input("Please input a new flowrate (0-10ml/min) ")
                                )
                            except ValueError as e:
                                print(
                                    f"{e}: is an invalid response, please choose a "
                                    "number"
                                )
                                continue

                            if raw_rate_float < 0 or raw_rate_float > 10:
                                print("please choose a number between 0–10 ml/min")
                                continue

                            else:
                                rate_rounded = round(raw_rate_float, 2)

                                if direction == "irun":
                                    new_rate = f"irate {rate_rounded} ml/min"
                                else:
                                    new_rate = f"wrate {rate_rounded} ml/min"

                                mode_commands["Mode"] = cont
                                mode_commands["Start"] = direction
                                mode_commands["Rate"] = new_rate
                                commands[mode_selection]["flow_command"] = new_rate

                                update_json(conn_settings, connection)

                                print("JSON UPDATED")
                                break
                    else:
                        print(f"{response} is an invalid response, please try again")
                        continue
                else:
                    print(f"{mode_selection} is an invalid response, please try again")
                    continue

        elif selection == "3":
            commands = connection["COMMANDS"][device_type].get(selection)

            mode = commands.get("Start")
            rate = commands.get("Rate")

            if mode == "irun":
                direction = "Fill the syringe(s)"
                rate_stripped = (rate.replace("irate", "")).strip()

            else:
                direction = "Empty the syringe(s)"
                rate_stripped = (rate.replace("wrate", "")).strip()

            while True:
                final_check = input(
                    f"Would you like to {direction} at a flowrate of {rate_stripped} "
                    "(y/n)"
                ).strip()
                if final_check.lower() == "n":
                    break

                elif final_check.lower() == "y":
                    print("Pump Starting")

                else:
                    print(f"{final_check} is an invalid response, please try again")
                    continue

                response = None
                for value in commands.values():
                    with PyConnection(device_type, conn_settings) as conn:
                        response = conn.send_serial(value)
                        time.sleep(1)

                print(f"Device primed with new settings: {response}")

                break

        elif selection == "4" or selection == "1":
            commands = connection["COMMANDS"][device_type].get(selection)

            with PyConnection(device_type, conn_settings) as conn:
                response = conn.send_serial(commands)
            print(f"Device response: {response}")
            continue

        else:
            print("You may need to select 'Setup' before you ask the pump to run")
            continue
