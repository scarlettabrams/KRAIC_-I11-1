from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import load_json

# Operational defaults for Focus_and_Lights.
# Soft limits should live in connection_settings.json and be applied by
# software_communication.py.
default_speed = 0.2


def focus_and_light_commands(device_type, conn_settings, equipment_initialisation):
    """Interactive menu for the two-motor focus and light Arduino controller"""

    connection = load_json(conn_settings)

    while True:
        print("\nFocus and Light Controller Menu\n")

        options = {
            "1": "Query Status",
            "2": "Enable Drivers",
            "3": "Disable Drivers",
            "4": "Stop Motion",
            "5": "Move Motor Absoulute(mm)",
            "6": "Move Motor Position(%)",
            "7": "Set LED Brightness",
            "8": "Calibrate Limits",
            "9": "Exit to Main Menu",
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

        if selection == "9":
            print("Returning to Main Menu")
            break

        command_base = connection["COMMANDS"][device_type].get(selection, {})

        if selection in ("2", "3"):
            with PyConnection(device_type, conn_settings) as conn:
                response = conn.send_serial(command_base)

                _print_response(response)

            continue

        motor = _input_motor()

        command_q = f"Q {motor}"

        with PyConnection(device_type, conn_settings) as conn:
            query_response = conn.send_serial(command_q)

        if query_response is None:
            print("No response from device")
            continue

        query_list_revs = query_response.split()

        (
            pos_mm,
            target_mm,
            running,
            enabled,
            low_mm,
            high_mm,
            spr,
            speed_mm,
            acc_mm,
            led1,
            led2,
        ) = query_conversion(query_list_revs)

        if selection == "1":
            print(
                "Device Response\n"
                f"Current Position: {pos_mm}mm"
                f"Target Position: {target_mm}mm"
                f"Running(1=Yes,0=No): {running}"
                f"Enabled(1=Yes,0=No): {enabled}"
                f"Low Limit: {low_mm}mm"
                f"High Limit: {high_mm}mm"
                f"Steps Per Rotation: {spr}"
                f"Current Speed: {speed_mm}mm/s"
                f"Current Acceleration: {acc_mm}mm/s^2"
                f"LED 1 Intensity: {led1}%"
                f"LED 2 Intensity: {led2}%"
            )

            continue

        if selection == "8":
            range_revs = calibrate_motor(
                device_type, conn_settings, motor, command_base, low_mm, high_mm
            )

            if range_revs:
                range_mm = range_revs * 0.5

                print(
                    "\nUser Limits\n\tLower limit - 0mm\n\tUpper limit - "
                    f"{range_mm}mm\n\tCurrent position - {range_mm}mm"
                )

                print("Calibration Complete!")

            continue

        command = _build_focus_command(
            selection, motor, command_base, low_mm, high_mm, pos_mm
        )

        if command is None:
            continue

        with PyConnection(device_type, conn_settings) as conn:
            response = conn.send_serial(command)

        _print_response(response)


def query_conversion(response_list):
    """change the queries in the list to mm"""

    values = [item.split("=")[1] for item in response_list[1:]]

    pos_mm = float(values[0]) * 0.5
    target_mm = float(values[1]) * 0.5
    running = bool(int(values[2]))
    enabled = bool(int(values[3]))
    low_mm = float(values[4]) * 0.5
    high_mm = float(values[5]) * 0.5
    spr = float(values[6])
    speed_mm = float(values[7]) * 0.5
    acc_mm = float(values[8]) * 0.5
    led1 = int(values[9])
    led2 = int(values[10])

    return (
        pos_mm,
        target_mm,
        running,
        enabled,
        low_mm,
        high_mm,
        spr,
        speed_mm,
        acc_mm,
        led1,
        led2,
    )


def _build_focus_command(selection, motor, command_base, low_mm, high_mm, pos_mm):
    """Build one Arduino command string from the selected menu option."""

    if selection == "4":
        return f"{command_base} {motor}"  # require recalibration if called

    if selection == "5":
        print(
            f"\nLow Limit: {low_mm}mm \nHigh Limit - {high_mm}mm \nCurrent Position - "
            f"{pos_mm}mm"
        )

        rev_delta = _input_float("Please write motion in mm, negatives allowed: ")

        potential_pos_mm = (rev_delta * 0.5) + pos_mm

        if potential_pos_mm < low_mm or potential_pos_mm > high_mm:
            print("This moves the stage outside of its user defined limits!")
            return None

        print(f"New Position = {potential_pos_mm}mm")

        return f"{command_base} {motor} {rev_delta} {default_speed}"

    if selection == "6":
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

        rev_delta = new_position_mm / 0.5

        print(f"New Position: {user_input}%")

        return f"{command_base} {motor} {rev_delta} {default_speed}"

    if selection == "7":
        percentage = _input_int("Please input the light intensity(%): ")

        return f"{command_base} {motor} {percentage}"

    print("No command built")
    return None


def _input_motor():
    """Prompt for motor 1 or 2."""

    while True:
        orientation = (
            input("Focus and Light orientation, Top (t) or Plane (p): ").strip().lower()
        )

        if orientation in ("t", "p"):
            if orientation == "t":
                motor = "2"
            else:
                motor = "1"

            return motor

        print("Please enter 1 or 2")


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


def _input_float(prompt, minimum=-5.0, maximum=5.0):
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

        value_rev = value * 2

        return value_rev


def _input_int(prompt, minimum=0, maximum=100):
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


def calibrate_motor(device_type, conn_settings, motor, command_base, low_mm, high_mm):
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

            change_lim = f"LIM {motor} -10 10"

            with PyConnection(device_type, conn_settings) as conn:
                conn.send_serial(change_lim)

            while True:
                rev_delta_neg = _input_float(
                    "Please move the motor (mm) to the most negative (starting) point: "
                )

                command = f"{command_base} {motor} {rev_delta_neg} {default_speed}"

                with PyConnection(device_type, conn_settings) as conn:
                    conn.send_serial(command)

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

                    zero_set = f"ZERO {motor}"

                    with PyConnection(device_type, conn_settings) as conn:
                        conn.send_serial(zero_set)

                    break

                else:
                    continue

            range_revs = 0

            while True:
                rev_delta_pos = _input_float(
                    "Please move the motor (mm) to the most positive point: "
                )

                range_revs = range_revs + rev_delta_pos

                command = f"{command_base} {motor} {rev_delta_pos} {default_speed}"

                with PyConnection(device_type, conn_settings) as conn:
                    conn.send_serial(command)

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

                    final_limits = f"LIM {motor} 0 {range_revs}"

                    with PyConnection(device_type, conn_settings) as conn:
                        conn.send_serial(final_limits)

                    return range_revs

                else:
                    continue

        print("Please select y/n")
