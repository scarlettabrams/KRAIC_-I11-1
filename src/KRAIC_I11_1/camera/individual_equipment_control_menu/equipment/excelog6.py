import time

from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import (
    load_json,
)

cal_wb_path = (
    "C:/Users/enybh/OneDrive - The University of Nottingham/Peahead/Postgrad/Year 4/"
    "venv/Sophie_data.xlsx"
)


def data_logger_commands(device_type, conn_settings, equipment_initialisation):
    """Defines all the possible commands you could need to run the KRAIC-G heating
    PXU
    """

    slave = 1

    connection = load_json(conn_settings)

    while True:
        print("\nData Logger Main Menu\n")

        options = {
            "1": "Test Command",
            "2": "All Channels",
            "3": "Channel 1",
            "4": "Channel 2",
            "5": "Channel 3",
            "6": "Channel 4",
            "7": "Exit to Main Menu",
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

        elif selection == "7":
            break

        else:
            commands = connection["COMMANDS"][device_type].get(selection)

        with PyConnection(device_type, conn_settings) as conn:
            address = commands[0]
            count = commands[1]
            response = conn.read_holding_registers(
                address=address, count=count, slave=slave
            )
            time.sleep(1)

        if response is None:
            print("No response from device")
            continue

        if selection == "2":
            kraic_raw_temp = response.registers

            if kraic_raw_temp[1] == 0:
                channel_1 = kraic_raw_temp[0] / 10
                print(f"Channel 1: {channel_1}°C")
            else:
                print("No thermocouple in Channel 1")

            if kraic_raw_temp[3] == 0:
                channel_2 = kraic_raw_temp[2] / 10
                print(f"Channel 2: {channel_2}°C")
            else:
                print("No thermocouple in Channel 2")

            if kraic_raw_temp[5] == 0:
                channel_3 = kraic_raw_temp[4] / 10
                print(f"Channel 3: {channel_3}°C")
            else:
                print("No thermocouple in Channel 3")

            if kraic_raw_temp[7] == 0:
                channel_4 = kraic_raw_temp[6] / 10
                print(f"Channel 4: {channel_4}°C")
            else:
                print("No thermocouple in Channel 4")

        elif selection == "1":
            try:
                status = response.registers[0]
                if status == 1:
                    time.sleep(1)
                    print("Device Ready")
            except TypeError:
                print("Device not Ready")

        else:
            number = int(selection) - 2
            try:
                kraic_raw_temp = response.registers
                if kraic_raw_temp[1] == 0:
                    channel_temp = kraic_raw_temp[0] / 10
                    print(f"Channel {number}: {channel_temp}°C")
            except (AttributeError, IndexError, TypeError):
                print(f"Channel {number} isn't connnected")
