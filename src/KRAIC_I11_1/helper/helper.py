# This is the module deisgned to give useful help methods that will support clean up
# of the automation scripts

import json
import sys
import time


def passwd(json1):
    """Check whether the user is eligible"""

    while True:
        clear_screen()

        print(
            "\nWelcome to the KRAIC-G Automation script script"
            "Please enter your Username and Password (or click 'q' to exit the script)"
            "\n"
        )

        username = input("Username: ")
        if username.lower() == "q":
            print("Exiting Script")
            exit()

        password = input("Password: ")
        if password.lower() == "q":
            print("Exiting Script")
            exit()

        time.sleep(0.5)
        print(
            "\nChecking User Credentials"
        )  # insert a json to retain the user credentials
        time.sleep(1)

        user_json = load_json(json1)

        user_check = user_json["USER_INFORMATION"].get(username)

        if user_check is None:
            print(
                f"User Credentials under the username {username} do not exist"
                "Please try again\n"
            )
            continue

        elif user_check == password:
            break

        else:
            print("\nIncorrect Password,\nPlease try again")
            continue

    print("\nUser Credentials Accepted")


def clear_screen(n=40):
    """line breaks making the screen appear like its empty"""

    print("\n" * n)


def load_json(json1: str):
    """load up the json with the index for the json list
    at the top of the KRAIC_Automation"""
    with open(json1) as f:
        value = json.load(f)

    return value


def dump_json(json1: str, name: str):
    """dump the changes you have made to the json
    to file by inputting index from list"""

    with open(json1, "w") as f:
        json.dump(name, f, indent=4)


def update_json(json1: str, name: str):
    """dumps the data into the json and then reloads
    it allowing us to read the new update values"""

    with open(json1, "w") as f:
        json.dump(name, f, indent=4)

    with open(json1) as f:
        value = json.load(f)

    return value


def list_dict(title: str, dictionary: dict):
    """takes a dictionary supplied and lists it"""

    print(f"{title.upper()}\n")

    for key, value in dictionary.items():
        print(f"{key}: {value}")


def response_refresh(lines: str):
    """allows to refresh code n number of lines"""

    move_n_lines = f"\033[{lines}A"
    sys.stdout.write(move_n_lines)
    sys.stdout.write("\033[0J")


def press_enter(prompt: str = "Press ENTER to continue or 'e' to exit"):
    """The choice of enter or exit"""

    while True:
        r = input(prompt)
        if r == "":
            return True
        elif r == "e":
            return False
        else:
            print("Invalid input — press ENTER.")
