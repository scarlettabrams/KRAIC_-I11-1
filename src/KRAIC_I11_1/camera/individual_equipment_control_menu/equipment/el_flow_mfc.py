from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import load_json, update_json

FULL_SCALE_FLOWRATE_ML_MIN = 11.0
PROPAR_MAX_SETPOINT = 32000


def format_propar(command_body):
    command_body = command_body.strip()

    if command_body.startswith(":"):
        command_body = command_body[1:]

    command_body = command_body.replace("\r", "").replace("\n", "")

    return f":{command_body}"


def flowrate_to_setpoint(flowrate_ml_min):
    if flowrate_ml_min < 0:
        raise ValueError("Flowrate cannot be negative.")

    if flowrate_ml_min > FULL_SCALE_FLOWRATE_ML_MIN:
        raise ValueError(
            f"Flowrate cannot exceed {FULL_SCALE_FLOWRATE_ML_MIN:.1f} ml/min."
        )

    return int(
        round((flowrate_ml_min / FULL_SCALE_FLOWRATE_ML_MIN) * PROPAR_MAX_SETPOINT)
    )


def setpoint_to_hex(setpoint):
    if setpoint < 0 or setpoint > PROPAR_MAX_SETPOINT:
        raise ValueError("Setpoint must be between 0 and 32000.")

    return f"{setpoint:04X}"


def build_set_flow_command(base_write_command, flowrate_ml_min):
    setpoint = flowrate_to_setpoint(flowrate_ml_min)
    setpoint_hex = setpoint_to_hex(setpoint)

    return format_propar(base_write_command + setpoint_hex)


def send_bronkhorst_command(device_type, command, conn_settings):
    with PyConnection(device_type, conn_settings) as conn:
        response = conn.send_serial(command)

    return response


def interpreter(response):

    value = int(response[-4:], 16)

    actual_value = (value / PROPAR_MAX_SETPOINT) * FULL_SCALE_FLOWRATE_ML_MIN

    print(f"\nFlowrate: {actual_value}ml/min")


def bronkhorst_mfc_commands(device_type, conn_settings, equipment_initialisation):

    connection = load_json(conn_settings)

    while True:
        connection = update_json(conn_settings, connection)

        commands = connection["COMMANDS"][device_type]

        print("\nBronkhorst MFC Menu\n")

        options = {
            "1": "Test Communication",
            "2": "Read Measured Flow",
            "3": "Read Current Setpoint",
            "4": "Set Flowrate",
            "5": "Stop Flow / Setpoint 0",
            "6": "Return to Main Menu",
        }

        for number, option in options.items():
            print(f"{number}: {option}")

        selection = input("\nPlease select an option from the list above: ")

        if selection not in options:
            print(f"'{selection}' is invalid. Please try again.")
            continue

        if selection == "6":
            print("Returning to individual equipment control menu")
            break

        elif selection == "1":
            command = format_propar(commands[selection])
            response = send_bronkhorst_command(device_type, command, conn_settings)
            print(f"\nDevice response: {response}")
            interpreter(response)

        elif selection == "2":
            command = format_propar(commands[selection])
            response = send_bronkhorst_command(device_type, command, conn_settings)
            print(f"\nMeasured flow response: {response}")
            interpreter(response)

        elif selection == "3":
            command = format_propar(commands[selection])
            response = send_bronkhorst_command(device_type, command, conn_settings)
            print(f"\nCurrent setpoint response: {response}")
            interpreter(response)

        elif selection == "4":
            while True:
                try:
                    flowrate = float(
                        input(
                            f"\nEnter desired N2 flowrate "
                            f"(0–{FULL_SCALE_FLOWRATE_ML_MIN:.1f} ml/min): "
                        )
                    )

                    command = build_set_flow_command(
                        base_write_command=commands[selection],
                        flowrate_ml_min=flowrate,
                    )

                except ValueError as e:
                    print(f"\nError: {e}")
                    continue

                print(f"\nRequested flowrate: {flowrate:.3f} ml/min")
                print(f"Command to send: {command}")

                confirm = input("Send this setpoint? (y/n): ").strip().lower()

                if confirm == "n":
                    break

                if confirm != "y":
                    print("Invalid response. Please enter y or n.")
                    continue

                response = send_bronkhorst_command(device_type, command, conn_settings)
                print(f"\nDevice response: {response}")
                break

        elif selection == "5":
            command = format_propar(commands[selection])
            response = send_bronkhorst_command(device_type, command, conn_settings)
            print(f"\nStop flow response: {response}")
