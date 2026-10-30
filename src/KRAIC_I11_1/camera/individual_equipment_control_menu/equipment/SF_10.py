from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import (
    load_json,
)


def sf_10_commands(device_type, conn_settings, equipment_initialisation):
    """Defines all the possible commands you could need to run the SF_10"""

    connection = load_json(conn_settings)

    while True:
        print("\nVapourtec SF_10 Peristaltic Pump Menu\n")

        options = {
            "1": "Test Command",
            "2": "Start Pump",
            "3": "Stop Pump",
            "4": "Set Flow Rate",
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
            break

        else:
            command = connection["COMMANDS"][device_type].get(selection)

        if selection == "4":
            while True:
                try:
                    raw_string = input(
                        "What flowrate would you like (0.02-10.00 ml/min): "
                    )
                    raw_float = float(raw_string)

                except ValueError as e:
                    print(f"\n{e} - Please type a number in the given range\n")
                    continue

                new_float = round(raw_float, ndigits=2)

                print(f"\nflowrate being sent : {new_float}")

                if new_float > 10 or new_float < 0.02:
                    print(
                        f"\n'{raw_float}' is outside the pumps flowrate limits - "
                        "please try again"
                    )
                    continue

                else:
                    new_string = str(new_float)
                    print(f"\nSetting pump flow rate to {new_string} ml/min")

                    command = command + new_string

                    print(f"Full command: {command}")

                    with PyConnection(device_type, conn_settings) as conn:
                        response = conn.send_serial(command)

                    print(f"Device response: {response}")

                    break

        elif selection == "5":
            with PyConnection(device_type, conn_settings) as conn:
                response = conn.send_serial(command)

                if response is None:
                    print("No response from device")
                    continue

                com_split = response.split(",")

                pump_status_no = float(com_split[0])
                pump_mode_no = float(com_split[1])
                tube_type_no = float(com_split[2])
                flowrate_no = float(com_split[3])
                dose_vol_no = float(com_split[4])
                ramp_start_no = float(com_split[5])
                ramp_end_no = float(com_split[6])
                ramp_time_no = float(com_split[7])
                gas_flow_no = float(com_split[8])
                osc_disp_no = float(com_split[9])
                osc_speed_no = float(com_split[10])
                pressure_trip_no = float(com_split[11])
                bpr_mode_sp_no = float(com_split[12])
                pump_pressure_no = float(com_split[13])

                if pump_status_no == 1:
                    pump_status = "ON"

                else:
                    pump_status = "OFF"

                if pump_mode_no == 0:
                    pump_mode = "FLOW"

                elif pump_mode_no == 1:
                    pump_mode = "REG"

                elif pump_mode_no == 2:
                    pump_mode = "DOSE"

                elif pump_mode_no == 3:
                    pump_mode = "RAMP"

                elif pump_mode_no == 4:
                    pump_mode = "GAS"

                else:
                    pump_mode = "OSC"

                if tube_type_no == 0:
                    tube_type = "Blue Tube"

                elif tube_type_no == 1:
                    tube_type = "Red Tube"

                elif tube_type_no == 2:
                    tube_type = "Green Tube"

                else:
                    tube_type = "Gold Tube"

                print(f"Status : {pump_status}")

                print(f"Pump Mode : {pump_mode}")

                print(f"Tube Type : {tube_type}")

                print(f"Flowrate : {flowrate_no / 1000} ml/min")

                print(f"Dose Volume : {dose_vol_no / 10} ml")

                print(f"Ramp Start Flowrate : {ramp_start_no / 1000} ml/min")

                print(f"Ramp End Flowrate : {ramp_end_no / 1000} ml/min")

                print(f"Ramp Time : {ramp_time_no / 10} minutes")

                print(f"Gas Flowrate : {gas_flow_no / 10} SCCM")

                print(f"Oscillation Displacement : {osc_disp_no} μl")

                print(f"Oscillator Speed : {osc_speed_no / 1000} ml/min")

                print(f"Pressure Trip Level : {pressure_trip_no / 1000} bar")

                print(f"BPR Mode Setpoint : {bpr_mode_sp_no / 1000} bar")

                print(f"Current Pump Pressure : {pump_pressure_no / 1000} bar")

        else:
            with PyConnection(device_type, conn_settings) as conn:
                response = conn.send_serial(command)

                print(f"{response}")
