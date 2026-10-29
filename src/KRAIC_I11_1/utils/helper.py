import json
import os


def load_json(path):
    """Load a JSON file, returning an empty dict if it doesn't exist yet."""

    if not os.path.exists(path):
        return {}

    with open(path) as f:
        return json.load(f)


def update_json(path, data):
    """Write data to a JSON file, replacing its contents."""

    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def list_dict(title, options):
    """Print a numbered menu of options under a title."""

    print(f"\n{title}")
    for key, value in options.items():
        print(f"  {key}. {value}")
