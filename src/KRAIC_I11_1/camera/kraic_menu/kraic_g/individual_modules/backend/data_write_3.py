import time

from openpyxl import load_workbook

from KRAIC_I11_1.camera.communication.software_communication import PyConnection
from KRAIC_I11_1.camera.helper.helper import (
    load_json,
)


def data_write(
    exp,
    flowrate_setting,
    julabo_command,
    heating_pxu_command,
    cal_wb_path,
    conn_settings,
    folder_name,
    cal_progress,
):
    """pulling all the non-visual data together for KRAIC-G calibration"""

    with PyConnection("Excelog_6", conn_settings) as conn:
        response = conn.read_holding_registers(address=4096, count=8, slave=1)
        time.sleep(1)

    if response is None:
        raise ConnectionError("No response from Excelog_6")
    kraic_raw_temp = response.registers

    if kraic_raw_temp[1] == 0:
        water_inlet = kraic_raw_temp[0] / 10
        print(f"Inlet Water Temperature : {water_inlet}°C")
    else:
        print("No thermocouple in Channel 1")
        water_inlet = 0

    if kraic_raw_temp[3] == 0:
        top_of_column = kraic_raw_temp[2] / 10
        print(f"Top of Column Temperature: {top_of_column}°C")
    else:
        print("No thermocouple in Channel 2")
        top_of_column = 0

    if kraic_raw_temp[5] == 0:
        water_outlet = kraic_raw_temp[4] / 10
        print(f"Outlet Water Temperature: {water_outlet}°C")
    else:
        print("No thermocouple in Channel 3")
        water_outlet = 0

    if kraic_raw_temp[7] == 0:
        ambient = kraic_raw_temp[6] / 10
        print(f"Ambient Temperature: {ambient}°C")
    else:
        print("No thermocouple in Channel 4")
        ambient = 0

    with PyConnection("JulaboFC600", conn_settings) as conn:
        julabo_pv_raw = conn.send_serial("in_pv_00")
        if julabo_pv_raw is None:
            raise ConnectionError("No response from JulaboFC600")
        julabo_pv = float(julabo_pv_raw)
        print(f"Julabo Process Value Temperature: {julabo_pv}°C")

    with PyConnection("Heating_PXU", conn_settings) as conn:
        response_raw = conn.read_holding_registers(address=0, count=1, slave=247)
        if response_raw is None:
            raise ConnectionError("No response from Heating_PXU")
        response_float = float(response_raw.registers[0])
        bottom_of_column = response_float / 10
        print(f"Bottom of Column Temperature: {bottom_of_column}°C")

    print(f"Flowrate: {flowrate_setting}ml/min")

    progress = load_json(cal_progress)

    coordinate = progress["CALIBRATION_STATUS"][folder_name]["Coordinates"]

    coordinate_1 = coordinate.get("y_top")
    coordinate_2 = coordinate.get("y_bottom")

    n = abs(coordinate_1 - coordinate_2) + 1

    data = (
        [
            exp,
            flowrate_setting,
            julabo_command,
            heating_pxu_command,
            julabo_pv,
            water_inlet,
            top_of_column,
        ]
        + n * [""]
        + [bottom_of_column, water_outlet, ambient, ""]
    )

    wb = load_workbook(cal_wb_path)
    ws = wb["Calibration Results"]

    ws.append(data)

    wb.save(cal_wb_path)

    return "Supporting data written to workbook"
