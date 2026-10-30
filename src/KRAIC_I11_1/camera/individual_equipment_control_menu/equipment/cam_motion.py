from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import (
    load_json,
)


def main_motion_commands(device_type, conn_settings, equipment_initialisation):
    """Defines all the possible commands needed to run the NEMA-23 main motion motor."""

    connection = load_json(conn_settings)

    while True:
        print("\nNEMA-23 Main Motion Menu\n")

        options = {
            "1": "Query Status",
            "2": "Enable Driver",
            "3": "Disable Driver",
            "4": "Stop Motion",
            "5": "Change Speed",
            "6": "Change Acceleration",
            "7": "Move Motor Absoulute(mm)",
            "8": "Move Motor Position(%)",
            "9": "Calibrate Limits",
            "10": "Exit to Main Menu",
        }

        for number, option in options.items():
            print(f"{number}: {option}")

        selection = input(
            "\nPlease select an option from the list above by selecting a number: "
        ).strip()

        if selection not in options:
            print(
                f"'{selection}' is an invalid selection: please select another option "
                "from the list above"
            )
            continue

        if selection == "10":
            print("Returning to Main Menu")
            break

        command_base = connection["COMMANDS"][device_type].get(selection, {})

        with PyConnection(device_type, conn_settings) as conn:
            query_response = conn.send_serial("Q")

        if query_response is None:
            print("No response from device")
            continue

        query_list_revs = query_response.split()

        pos_mm, target_mm, running, enabled, low_mm, high_mm, spr, speed_mm, acc_mm = (
            query_conversion(query_list_revs)
        )

        if selection in ("2", "3", "4"):
            with PyConnection(device_type, conn_settings) as conn:
                response = conn.send_serial(command_base)

                _print_response(response)

            continue

        if selection == "1":
            print(
                "Device Response\n"
                f"Current Position: {pos_mm}mm\n"
                f"Target Position: {target_mm}mm\n"
                f"Running: {running}\n"
                f"Enabled: {enabled}\n"
                f"Low Limit: {low_mm}mm\n"
                f"High Limit: {high_mm}mm\n"
                f"Steps Per Rotation: {spr}\n"
                f"Current Speed: {speed_mm}mm/s\n"
                f"Current Acceleration: {acc_mm}mm/s^2\n"
            )

            continue

        if selection == "9":
            command = calibrate_motor(
                device_type, conn_settings, command_base, low_mm, high_mm
            )

            if command:
                with PyConnection(device_type, conn_settings) as conn:
                    response = conn.send_serial(command)

                print("Calibration Complete!")

            continue

        command = _build_motion_command(
            selection, command_base, low_mm, high_mm, pos_mm
        )

        if command is None:
            continue

        with PyConnection(device_type, conn_settings) as conn:
            response = conn.send_serial(command)

        _print_response(response)


def _build_motion_command(selection, command_base, low_mm, high_mm, pos_mm):
    """Build one Arduino command string from the selected menu option."""

    if selection == "5":
        speed = _input_float(
            "Please input a speed (mm/s): ", minimum=1, maximum=20
        )  # speed

        return f"{command_base} {speed}"

    if selection == "6":
        acceleration = _input_float(
            "Please input an acceleration (mm/s^2): ", minimum=1, maximum=60
        )  # acceleration

        return f"{command_base} {acceleration}"

    if selection == "7":
        print(
            f"\nLow Limit: {low_mm}mm \nHigh Limit - {high_mm}mm \nCurrent Position - "
            f"{pos_mm}mm"
        )

        rev_delta = _input_float("Please write motion in mm, negatives allowed: ")

        potential_pos_mm = (rev_delta * 60) + pos_mm

        if potential_pos_mm < low_mm or potential_pos_mm > high_mm:
            print("This moves the stage outside of its user defined limits!")
            return None

        print(f"New Position = {potential_pos_mm}mm")

        return f"{command_base} {rev_delta}"

    if selection == "8":
        current_per = (pos_mm / (high_mm - low_mm)) * 100

        print(f"\nCurrent Position on Stage: {current_per}%")

        while True:
            user_input = input("How far along the stage wouly you like to move(%)?: ")

            try:
                user_int = int(user_input)

                if user_int >= 0 and user_int <= 100:
                    break
                else:
                    print("Please input and integer between 0-100")
                    continue

            except ValueError:
                print("Please input and integer between 0-100")

                continue

        user_float = float(user_int)

        new_position_mm = (user_float / 100) * (high_mm - low_mm)

        rev_delta = new_position_mm / 60

        print(f"New Position: {user_input}%")

        return f"{command_base} {rev_delta}"

    print("No command built")
    return None


def query_conversion(response_list):
    """change the queries in the list to mm"""

    values = [item.split("=")[1] for item in response_list[0:]]

    pos_mm = float(values[0]) * 60
    target_mm = float(values[1]) * 60
    running = bool(int(values[2]))
    enabled = bool(int(values[3]))
    low_mm = float(values[4]) * 60
    high_mm = float(values[5]) * 60
    spr = float(values[6])
    speed_mm = float(values[7]) * 60
    acc_mm = float(values[8]) * 60

    return pos_mm, target_mm, running, enabled, low_mm, high_mm, spr, speed_mm, acc_mm


def _print_response(response):
    """Print responses returned by PyConnection.send_serial in a readable way."""

    if response is None:
        print("Device response: None")
        return

    if isinstance(response, list):
        if len(response) == 0:
            print("Device response: (no response)")
        else:
            for line in response:
                print(f"Device response: {line}")
        return

    print(f"Device response: {response}")


def _input_float(prompt, minimum=-500, maximum=500):
    while True:
        try:
            value = float(input(prompt))
        except ValueError as e:
            print(f"\n{e} - Please type a number\n")
            continue

        if minimum is not None and value < minimum:
            print(f"Value is below the minimum allowed value of {minimum}mm")
            continue

        if maximum is not None and value > maximum:
            print(f"Value is above the maximum allowed value of {maximum}mm")
            continue

        value_rev = value / 60

        return value_rev


def _input_int(prompt, minimum=None, maximum=None):
    while True:
        try:
            value = int(input(prompt))
        except ValueError as e:
            print(f"\n{e} - Please type a whole number\n")
            continue

        if minimum is not None and value < minimum:
            print(f"Value is below the minimum allowed value of {minimum}")
            continue

        if maximum is not None and value > maximum:
            print(f"Value is above the maximum allowed value of {maximum}")
            continue

        return value


def calibrate_motor(device_type, conn_settings, command_base, low_mm, high_mm):
    """Allow the user to define the high and low limits of operation"""

    while True:
        print(
            "\nThis setting allows you to move the motor past stage limits, please "
            "move stage with caution!!!\n"
        )
        change = input("Would you like to recalibrate motor (y/n): ").strip().lower()

        if change in ("y", "n"):
            if change == "n":
                return None

            with PyConnection(device_type, conn_settings) as conn:
                response = conn.send_serial("LIM -10 10")

            while True:
                rev_delta_neg = _input_float(
                    "Please move the motor (mm) to the most negative (starting) point: "
                )

                command = f"{command_base} {rev_delta_neg}"

                with PyConnection(device_type, conn_settings) as conn:
                    response = conn.send_serial(command)

                while True:
                    confirm = (
                        input(
                            "Would you like to move the motor again to reach the most "
                            "negative position(y/n)?  "
                        )
                        .strip()
                        .lower()
                    )

                    if confirm not in ("y", "n"):
                        print("Please select y/n")
                        continue

                    break

                if confirm == "n":
                    print(
                        "confirming minimum extremity of range\nSetting position to "
                        "zero\n"
                    )

                    with PyConnection(device_type, conn_settings) as conn:
                        response = conn.send_serial("ZERO")

                    break

                else:
                    continue

            range_revs = 0

            while True:
                rev_delta_pos = _input_float(
                    "Please move the motor (mm) to the most positive point: "
                )

                range_revs = range_revs + rev_delta_pos

                command = f"{command_base} {rev_delta_pos}"

                with PyConnection(device_type, conn_settings) as conn:
                    response = conn.send_serial(command)

                    _print_response(response)

                while True:
                    confirm = (
                        input(
                            "Would you like to move the motor again to reach the most "
                            "positive position(y/n)?  "
                        )
                        .strip()
                        .lower()
                    )

                    if confirm not in ("y", "n"):
                        print("Please select y/n")
                        continue
                    else:
                        break

                if confirm == "n":
                    print("confirming maximum extremity of range\nChanging Limits\n")
                    return f"LIM 0 {range_revs}"

                else:
                    continue

        print("Please select y/n")
