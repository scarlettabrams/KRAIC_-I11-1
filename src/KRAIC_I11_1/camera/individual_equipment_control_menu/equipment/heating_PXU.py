import json
import time

from KRAIC_I11_1.camera.communication.software_communication import PyConnection


def heating_pxu_commands(device_type, conn_settings, equipment_initialisation):
    """Defines all the possible commands you could need to run the KRAIC-G heating
    PXU
    """

    slave = 247

    print("Accessing remote control options ")

    with open(conn_settings) as f:
        connection = json.load(f)

    while True:
        commands = []

        print("\nKRAIC-G Heating PXU Main Menu\n")

        options = {
            "1": "Test Command",
            "2": "Process Value",
            "3": "Active Setpoint",
            "4": "PID Parameters",
            "5": "Exit to Main Menu",
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

        elif selection == "5":
            break

        else:
            route = connection["COMMANDS"][device_type][selection]

        if selection == "4":
            commands = []

            while True:
                pid_options = {
                    "1": "Manually Set",
                    "2": "Autotune",
                    "3": "Current Values",
                    "4": "Return to Main Menu",
                }

                for key, value in pid_options.items():
                    print(f"{key}: {value}")

                pid_selection = input(
                    "\nPlease select an option from the list above by selecting a "
                    "number: "
                )

                if pid_selection == "1":
                    while True:
                        try:
                            p_input = float(
                                input(
                                    "Please select a value for the proportional band "
                                    "(1-999): "
                                )
                            )
                            p_write = route[pid_selection].get("P")
                            i_input = float(
                                input(
                                    "Please select a value for the integral time "
                                    "(0-999): "
                                )
                            )
                            i_write = route[pid_selection].get("I")
                            d_input = float(
                                input(
                                    "Please select a value for the derivative "
                                    "time(0-999): "
                                )
                            )
                            d_write = route[pid_selection].get("D")

                        except ValueError as e:
                            print(
                                f"{e}: is not an acceptable input - please input a "
                                "number"
                            )
                            continue

                        if (
                            1 <= p_input <= 999
                            and 0 <= i_input <= 999
                            and 0 <= d_input <= 999
                        ):
                            p_final = round(p_input, ndigits=2)
                            i_final = round(i_input, ndigits=2)
                            d_final = round(d_input, ndigits=2)
                            time.sleep(1)
                            print("\nValues Accepted\n")
                            break

                        else:
                            time.sleep(1)
                            print(
                                "\nPlease select a number within the ranges stated "
                                "above\n"
                            )
                            continue

                    p_write[1] = p_final
                    route[pid_selection]["P"] = p_write
                    commands.append(p_write)
                    i_write[1] = i_final
                    route[pid_selection]["I"] = i_write
                    commands.append(i_write)
                    d_write[1] = d_final
                    route[pid_selection]["D"] = d_write
                    commands.append(d_write)

                    time.sleep(1)
                    print("Saving Command")
                    time.sleep(1)

                elif pid_selection == "2":
                    while True:
                        try:
                            auto_input = float(
                                input(
                                    "Please select a temperature to autotune PID "
                                    "Parameters towards (30-60°C): "
                                )
                            )
                            auto_write = route.get(pid_selection)

                        except ValueError as e:
                            print(
                                f"{e}: is not an acceptable input - please input a "
                                "number"
                            )
                            continue

                        if 30 <= auto_input <= 60:
                            auto_final = round(auto_input, ndigits=1)
                            print("\nValue Accepted\n")
                            break

                        else:
                            print(
                                "\nPlease select a number within the ranges stated "
                                "above\n"
                            )
                            continue

                    auto_write[1] = auto_final
                    route[pid_selection] = auto_write

                    commands.append(auto_write)

                elif pid_selection == "3":
                    current_values = route.get(pid_selection)

                    commands.append(current_values)

                elif pid_selection == "4":
                    print("Returning to Heating PXU main menu")
                    break

                else:
                    print(
                        f"{pid_selection} is an invalid selection - please input a "
                        "number between 1-4"
                    )
                    continue

                with open(conn_settings, "w") as f:
                    json.dump(connection, f, indent=4)

                if pid_selection == "1" or pid_selection == "2":
                    with PyConnection(device_type, conn_settings) as conn:
                        for command in commands:
                            address = command[0]
                            value = command[1]

                            response = conn.write_register(address, value, slave)
                            time.sleep(1)
                            print(f"\nDevice response: {response}")

                            time.sleep(1)
                else:
                    with PyConnection(device_type, conn_settings) as conn:
                        for command in commands:
                            address = command[0]
                            count = command[1]

                            response = conn.read_holding_registers(
                                address, count, slave
                            )
                            time.sleep(1)
                            print(f"\nDevice response: {response}")

        elif selection == "3":
            while True:
                commands = []
                read_sp = route.get("Read")
                commands.append(read_sp)

                address = read_sp[0]
                count = read_sp[1]

                with PyConnection(device_type, conn_settings) as conn:
                    response = conn.read_holding_registers(
                        address=address, count=count, slave=slave
                    )

                print(f"\nCurrent setpoint is {response}°C\n")
                binary = input("Would you like to select a new setpoint(y/n)?  ")

                if binary.lower() == "n":
                    break

                elif binary.lower() == "y":
                    while True:
                        commands = []
                        try:
                            sp_input = float(
                                input("Please select a SP temperature (30-60°C): ")
                            )
                            sp_write = route.get("Write")

                        except ValueError as e:
                            print(
                                f"{e}: is not an acceptable input - please input a "
                                "number"
                            )
                            continue

                        if 30 <= sp_input <= 60:
                            sp_final = (round(sp_input, ndigits=1)) * 10
                            sp_final = int(round(sp_final, ndigits=0))
                            time.sleep(1)
                            print("\nValue Accepted\n")
                            break

                        else:
                            print(
                                "\nPlease select a number within the ranges stated "
                                "above\n"
                            )
                            continue

                    sp_write[1] = sp_final
                    route["Write"] = sp_write

                    with open(conn_settings, "w") as f:
                        json.dump(connection, f, indent=4)

                    commands.append(sp_write)

                    time.sleep(1)

                    with PyConnection(device_type, conn_settings, slave) as conn:
                        address = sp_write[0]
                        value = sp_write[1]

                        response = conn.write_register(
                            address=address, value=value, slave=slave
                        )
                        time.sleep(1)
                        if response is None:
                            print("No response from device")
                            break
                        raw_temp = float(response.registers[0])
                        actual_temp = raw_temp / 10

                        print(f"Current Setpoint Value : {actual_temp}°C")

                        break

                else:
                    print(f"{binary} is an invalid response, please select y/n")
                    continue

        else:
            route2 = connection["COMMANDS"][device_type].get(selection)

            address = route2[0]
            count = route2[1]

            with PyConnection(device_type, conn_settings) as conn:
                response = conn.read_holding_registers(
                    address=address, count=count, slave=slave
                )

            if response is None:
                print("No valid Modbus response received")
                return
            if response.isError():
                print(f"Modbus error response: {response}")
                return

            if not hasattr(response, "registers") or not response.registers:
                print(f"Response had no registers: {response}")
                return

            if selection == "1":
                if response.status == 1:
                    print("Device Ready")
                else:
                    print("Device not Ready")
            else:
                raw_temp = float(response.registers[0])
                actual_temp = raw_temp / 10

                print(f"Current Process Value : {actual_temp}°C")
