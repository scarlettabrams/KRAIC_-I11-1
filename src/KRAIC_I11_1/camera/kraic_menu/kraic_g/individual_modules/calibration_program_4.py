from KRAIC_I11_1.camera.helper.helper import (
    load_json,
    update_json,
)

from .backend.cal_ramp_2 import (
    ramp_program,
)


def run_calibration_program(
    folder_name,
    wb_path,
    cal_progress,
    conn_settings,
    equipment_initialisation,
    gear_pump_path,
):
    """the main program that handles the commands and the execution of the experimental
    matrix
    """

    progress = load_json(cal_progress)

    state = progress["CALIBRATION_STATUS"][folder_name].get("Calibration", {})
    # Provide safe defaults if something is missing

    temp_dict = state["Temperature_commands"]

    experiment_num = state.get("Experiment", 0)

    print("\nRunning calibration sequence...\n")
    # ramp_program is expected to return (commands, experiment, flowrate_setting,
    # flow_exp(the experiment number at a given flowrate))

    heating_keys = list(temp_dict.keys())

    for heating in heating_keys:
        heating_i = int(round(float(heating), 0))
        julabo_list = list(temp_dict.get(heating, []))

        for julabo in julabo_list:
            full_flow_list = list(state["Flow_commands"])  # copy the json flow list
            current_flow = state["Current_flow"]

            start_i = full_flow_list.index(current_flow)
            flows_to_run = full_flow_list[start_i:]

            for flow in flows_to_run:
                experiment_num, reason = ramp_program(
                    julabo,
                    heating_i,
                    wb_path,
                    experiment_num,
                    flow,
                    conn_settings,
                    equipment_initialisation,
                    gear_pump_path,
                    folder_name,
                    cal_progress,
                )  # main ramp program

                print(f"Returned: experiment_num = {experiment_num}, reason = {reason}")

                if reason == "unreachable":
                    print(
                        "Setpoint unreachable - skipping this JULABO setpoint condition"
                    )

                    state["Current_flow"] = full_flow_list[0]

                    commands_out = cross_off(temp_dict, heating, julabo)
                    state["Temperature_commands"] = commands_out
                    state["Experiment"] = experiment_num

                    # If no commands left, calibration is done
                    if not commands_out:
                        state["Status"] = True
                        print("Calibration program completed.")

                        update_json(cal_progress, progress)
                        return

                    update_json(cal_progress, progress)
                    return

                else:
                    i = full_flow_list.index(flow)

                    try:
                        next_flowrate = full_flow_list[i + 1]
                        state["Current_flow"] = next_flowrate
                        pass

                    except IndexError:
                        state["Current_flow"] = full_flow_list[0]

                        commands_out = cross_off(temp_dict, heating, julabo)
                        state["Temperature_commands"] = commands_out

                        # Finishing off
                        if not commands_out:
                            state["Status"] = True
                            print("Calibration program completed.")
                            print(
                                f"Saving: Experiment = {state['Experiment']},"
                                f"Current Flowrate = {state['Current_flow']},"
                            )
                            update_json(cal_progress, progress)
                            return

                    state["Experiment"] = experiment_num
                    update_json(cal_progress, progress)

                while True:
                    next_step = input(
                        "Would you like to continue with the next calibration "
                        "experiments (y/n)? "
                    )

                    if next_step == "y":
                        print("Next step in calibration: ")
                        break

                    elif next_step == "n":
                        return

                    else:
                        print("This is an invalid response, try again")
                        continue


def cross_off(temp_dict, key, value):
    """Removes `value` from commands[key].

    If commands[key] becomes empty, removes the key entirely. Returns the updated
    commands dictionary.
    """

    # If the key doesn't exist, do nothing
    if key not in temp_dict:
        return temp_dict

    # Remove the value if it exists
    if value in temp_dict[key]:
        temp_dict[key].remove(value)

    # Remove the key if its list is now empty
    if not temp_dict[key]:
        del temp_dict[key]

    return temp_dict
