import sys
import time

from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.individual_equipment_control_menu.equipment.reglo_z import (
    command_setting,
)

from .data_write_3 import (
    data_write,
)


def response_refresh(
    lines,
    poll_interval,
):
    """allows to refresh code n number of lines"""

    move_n_lines = f"\033[{lines}A"
    sys.stdout.write(move_n_lines)
    sys.stdout.write("\033[0J")

    time.sleep(poll_interval)


def wait_for_setpoint(
    julabo_command,
    heating_command,
    conn_settings,
    timeout_reached=120,
    timeout_unreachable=600,
    poll_interval=2,
):
    """
    Poll Julabo and PXU until conditions are met.
    Returns (reason)
    reason: 'reached' | 'unreachable' |
    """

    print("Heating PXU PV: --.-°C")
    print("Julabo PV: --.-°C")
    print("Time elapsed: - s")  # we print 3 lines

    flag = True

    while flag:  # we open the loop cause flag = True
        with PyConnection("Heating_PXU", conn_settings) as conn:
            pv1_raw = conn.read_holding_registers(address=0, count=1, slave=247)
            if pv1_raw is None:
                raise ConnectionError("No response from Heating_PXU")
            pv1_float = float(pv1_raw.registers[0])

        heating_pv1 = pv1_float  # the first read value of the heating PXU

        with PyConnection("JulaboFC600", conn_settings) as conn:
            julabo_pv1_raw = conn.send_serial("in_pv_00")
            if julabo_pv1_raw is None:
                raise ConnectionError("No response from JulaboFC600")
            julabo_pv1 = float(julabo_pv1_raw)

        start_time = time.time()

        if (
            abs(julabo_pv1 - float(julabo_command)) <= 0.5
        ):  # if the julabo SP is within 0.5oC of its SP we can move on
            while True:
                with PyConnection("Heating_PXU", conn_settings) as conn:
                    heating_pv_raw = conn.read_holding_registers(
                        address=0, count=1, slave=247
                    )
                    if heating_pv_raw is None:
                        raise ConnectionError("No response from Heating_PXU")
                    heating_pv = float(heating_pv_raw.registers[0])

                with PyConnection("JulaboFC600", conn_settings) as conn:
                    julabo_pv_raw = conn.send_serial("in_pv_00")
                    if julabo_pv_raw is None:
                        raise ConnectionError("No response from JulaboFC600")
                    julabo_pv = float(julabo_pv_raw)

                time_elapsed_1 = time.time() - start_time
                time_elapsed = round(time_elapsed_1, ndigits=2)

                response_refresh(3, poll_interval)

                print(f"Heating PXU PV: {heating_pv / 10}°C")
                print(f"Julabo PV: {julabo_pv}°C")
                print(f"Time elapsed: {time_elapsed}s")

                if abs(heating_pv - heating_pv1) > 0:
                    # the value of heating_pv is far away from heating_pv1 so we need to
                    # reset heating pv_1
                    flag = True
                    break

                elif (
                    abs(heating_pv - heating_pv1) <= 1
                    and time_elapsed >= timeout_unreachable
                ):
                    # we havent reached the setpoint but the value isnt changing a huge
                    # amount either in unreachable time
                    flag = False
                    return "unreachable"  # we return its unreachable
                    break

                elif (
                    abs(heating_pv - heating_command) <= 0
                    and time_elapsed >= timeout_reached
                ):
                    # we have reached our setpoint and it has stayed for reachable time
                    # and can therefore exit
                    flag = False
                    return "reached"  # we return we reached the SP
                    break

                else:
                    # should only be found when we are simply waiting for time to pass
                    # because none of 3 conditions above are met
                    continue
        else:
            time_elapsed_1 = time.time() - start_time
            time_elapsed = round(time_elapsed_1, ndigits=2)

            response_refresh(3, poll_interval)

            print(f"Heating PXU PV: {heating_pv1 / 10}°C")
            print(f"Julabo PV: {julabo_pv1}°C")
            print(f"Time elapsed: {time_elapsed}s")


def run_single_experiment(
    exp,
    flowrate_setting,
    julabo_command,
    heating_command,
    cal_wb_path,
    conn_settings,
    folder_name,
    cal_progress,
):
    # Write data, prompt for photo etc. (wraps data_write)

    while True:
        resp = input(
            "Please take a Picture of the KRAIC-G column using the disconnected "
            "FLIR-E5 then press 'Enter' to proceed"
        )
        if resp == "":
            print("Single Experiment completed - writing data")
            response = data_write(
                exp,
                flowrate_setting,
                julabo_command,
                heating_command,
                cal_wb_path,
                conn_settings,
                folder_name,
                cal_progress,
            )
            print(response)
            break
        else:
            print("Invalid response, press Enter to continue")


def ramp_program(
    julabo,
    heating_i,
    cal_wb_path,
    exp,
    flow,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
    folder_name,
    cal_progress,
):
    """
    High level program that iterates commands and returns updated state.
    commands: dict {heating: [julabo_temps]}
    """

    flowrate_setting = flow

    exp = exp + 1

    print(
        f"Experiment {exp}: flowrate {flowrate_setting}, julabo {julabo}, heating "
        f"{heating_i / 10}"
    )
    # send devices

    command_setting(
        flowrate_setting,
        conn_settings,
        equipment_initialisation,
        gear_pump_path,
        device_type="Gear_Pump",
        selection="2",
    )  # flowrate command
    time.sleep(120)
    with PyConnection("JulaboFC600", conn_settings) as conn:
        conn.send_serial(f"out_sp_00 {julabo}")  # julabo temperature command
    with PyConnection("Heating_PXU", conn_settings) as conn:
        conn.write_register(
            address=1, value=heating_i, slave=247
        )  # heating_PXU command

    reason = wait_for_setpoint(julabo, heating_i, conn_settings)

    print(f"Run classed as: {reason}")

    if reason == "unreachable":
        print("Heating PXU setpoint not reached")
        exp = exp - 1

    else:
        run_single_experiment(
            exp,
            flowrate_setting,
            julabo,
            heating_i,
            cal_wb_path,
            conn_settings,
            folder_name,
            cal_progress,
        )

    return exp, reason
