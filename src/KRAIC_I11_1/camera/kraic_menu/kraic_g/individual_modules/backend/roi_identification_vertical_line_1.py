import os

import numpy as np
from flirimageextractor import FlirImageExtractor
from matplotlib import pyplot as plt


def interactive_roi_selection(image_paths, display_width=1200):
    """
    Display the radiometric thermal array from the first FLIR image and allow
    the user to select a vertical temperature-extraction line.

    The user clicks twice:
        1. The end of the line closest to the solution inlet.
        2. The end of the line closest to the solution outlet.

    The x-coordinate from the first click is used for both endpoints, ensuring
    that the selected line is perfectly vertical.

    Parameters
    ----------
    image_paths : list[str]
        Paths to candidate FLIR radiometric images. The first valid image is
        used for ROI selection.

    display_width : int
        Retained for compatibility with the previous function signature.
        Matplotlib controls the displayed size; the thermal coordinates remain
        unchanged regardless of the displayed window size.

    Returns
    -------
    dict | None
        A dictionary containing thermal-array coordinates:

        {
            "x": int,
            "y_top": int,
            "y_bottom": int
        }

        Returns None if the user quits without confirming.
    """

    if not image_paths:
        raise ValueError("image_paths must contain at least one FLIR image path.")

    # -------------------------------------------------------------------------
    # Locate the first image that can successfully produce a thermal array.
    # -------------------------------------------------------------------------

    thermal = None
    selected_image_path = None
    last_error = None

    for image_path in image_paths:
        if not os.path.isfile(image_path):
            continue

        try:
            extractor = FlirImageExtractor()
            extractor.process_image(image_path)
            candidate_thermal = extractor.get_thermal_np()

            if candidate_thermal is None:
                raise ValueError("get_thermal_np() returned None.")

            candidate_thermal = np.asarray(candidate_thermal)

            if candidate_thermal.ndim != 2:
                raise ValueError(
                    "Expected a two-dimensional thermal array, "
                    f"but received shape {candidate_thermal.shape}."
                )

            if candidate_thermal.size == 0:
                raise ValueError("The extracted thermal array is empty.")

            if not np.isfinite(candidate_thermal).any():
                raise ValueError(
                    "The extracted thermal array contains no finite values."
                )

            thermal = candidate_thermal
            selected_image_path = image_path
            break

        except Exception as exc:
            last_error = exc
            print(f"Warning: could not extract thermal data from {image_path}: {exc}")

    if thermal is None:
        raise RuntimeError(
            "No usable radiometric thermal image was found in image_paths. "
            f"Last extraction error: {last_error}"
        )

    thermal_h, thermal_w = thermal.shape

    print("\nThermal ROI selection image loaded successfully.")
    print(f"Image: {selected_image_path}")
    print(f"Thermal-array shape: {thermal_h} rows × {thermal_w} columns")
    print(f"Valid x coordinates: 0 to {thermal_w - 1}")
    print(f"Valid y coordinates: 0 to {thermal_h - 1}")

    # -------------------------------------------------------------------------
    # Interactive selection helper.
    # -------------------------------------------------------------------------

    def select_two_points():
        """
        Display the thermal array and collect two clicks.

        The x-coordinate of the first click is used for both endpoints so the
        resulting extraction line is vertical.
        """

        clicked_points = []
        selected_line: dict[str, tuple[int, int, int] | None] = {"coords": None}

        fig, ax = plt.subplots(figsize=(12, 8))

        thermal_image = ax.imshow(
            thermal, cmap="inferno", origin="upper", interpolation="nearest"
        )

        colorbar = fig.colorbar(thermal_image, ax=ax)
        colorbar.set_label("Temperature (°C)")

        ax.set_title(
            "Select the vertical thermal extraction line\n"
            "1. Click the end closest to the solution inlet.\n"
            "2. Click the end closest to the solution outlet.\n"
            "The first click's x-coordinate will be used for the full line."
        )

        ax.set_xlabel("Thermal-array x coordinate")
        ax.set_ylabel("Thermal-array y coordinate")

        # Keep the axes matched exactly to valid thermal-array indices.
        ax.set_xlim(-0.5, thermal_w - 0.5)
        ax.set_ylim(thermal_h - 0.5, -0.5)

        (line_artist,) = ax.plot([], [], color="cyan", linewidth=2)

        (point_artist,) = ax.plot(
            [], [], marker="o", linestyle="None", color="cyan", markersize=7
        )

        coordinate_text = ax.text(
            0.02,
            0.98,
            "",
            transform=ax.transAxes,
            verticalalignment="top",
            horizontalalignment="left",
            color="white",
            bbox={"facecolor": "black", "alpha": 0.65, "edgecolor": "none"},
        )

        def redraw():
            if len(clicked_points) == 0:
                point_artist.set_data([], [])
                line_artist.set_data([], [])
                coordinate_text.set_text("")

            elif len(clicked_points) == 1:
                x1, y1 = clicked_points[0]

                point_artist.set_data([x1], [y1])
                line_artist.set_data([], [])

                coordinate_text.set_text(f"First point: x={x1}, y={y1}")

            elif len(clicked_points) == 2:
                x1, y1 = clicked_points[0]
                _, y2 = clicked_points[1]

                point_artist.set_data([x1, x1], [y1, y2])

                line_artist.set_data([x1, x1], [y1, y2])

                coordinate_text.set_text(f"Vertical line: x={x1}, y={y1} to y={y2}")

            fig.canvas.draw_idle()

        def on_click(event):
            if event.inaxes != ax:
                return

            if event.xdata is None or event.ydata is None:
                return

            # Ignore any further clicks after the two endpoints are selected.
            if len(clicked_points) >= 2:
                return

            x_clicked = int(round(event.xdata))
            y_clicked = int(round(event.ydata))

            # Clip directly to the thermal-array bounds.
            x_clicked = max(0, min(x_clicked, thermal_w - 1))

            y_clicked = max(0, min(y_clicked, thermal_h - 1))

            clicked_points.append((x_clicked, y_clicked))

            redraw()

            if len(clicked_points) == 2:
                x_first = clicked_points[0][0]
                y_first = clicked_points[0][1]
                y_second = clicked_points[1][1]

                selected_line["coords"] = (x_first, y_first, y_second)

                print("\nVertical line selected directly on thermal array:")
                print(f"x={x_first}, first y={y_first}, second y={y_second}")
                print("Close the thermal-image window to continue.")

        fig.canvas.mpl_connect("button_press_event", on_click)

        plt.tight_layout()
        plt.show()

        # Ensure the figure does not remain allocated after it is closed.
        plt.close(fig)

        return selected_line["coords"]

    # -------------------------------------------------------------------------
    # Repeat selection until confirmed or cancelled.
    # -------------------------------------------------------------------------

    while True:
        selected_coordinates = select_two_points()

        if selected_coordinates is None:
            action = (
                input(
                    "\nNo complete line was selected. "
                    "Enter 'r' to retry or 'q' to quit: "
                )
                .strip()
                .lower()
            )

            if action == "q":
                print("Quitting without saving thermal coordinates.")
                return None

            print("Restarting thermal-line selection.")
            continue

        x_selected, y1_selected, y2_selected = selected_coordinates

        # The coordinates are already thermal-array coordinates because the
        # user clicked directly on the extracted thermal array.
        x_selected = max(0, min(int(x_selected), thermal_w - 1))

        y1_selected = max(0, min(int(y1_selected), thermal_h - 1))

        y2_selected = max(0, min(int(y2_selected), thermal_h - 1))

        line_definition = {
            "x": x_selected,
            "y_top": min(y1_selected, y2_selected),
            "y_bottom": max(y1_selected, y2_selected),
        }

        number_of_pixels = line_definition["y_bottom"] - line_definition["y_top"] + 1

        print("\nThermal-array vertical line:")
        print(line_definition)
        print(f"Number of thermal pixels on the line: {number_of_pixels}")

        # ---------------------------------------------------------------------
        # Confirmation plot.
        # ---------------------------------------------------------------------

        fig, ax = plt.subplots(figsize=(12, 8))

        thermal_image = ax.imshow(
            thermal, cmap="inferno", origin="upper", interpolation="nearest"
        )

        colorbar = fig.colorbar(thermal_image, ax=ax)
        colorbar.set_label("Temperature (°C)")

        ax.plot(
            [line_definition["x"], line_definition["x"]],
            [line_definition["y_top"], line_definition["y_bottom"]],
            color="cyan",
            linewidth=2,
        )

        ax.scatter(
            [line_definition["x"], line_definition["x"]],
            [line_definition["y_top"], line_definition["y_bottom"]],
            color="cyan",
            s=60,
        )

        ax.set_title(
            "Thermal extraction line confirmation\n"
            f"x={line_definition['x']}, "
            f"y={line_definition['y_top']} "
            f"to {line_definition['y_bottom']}\n"
            f"{number_of_pixels} thermal pixels will be extracted."
        )

        ax.set_xlabel("Thermal-array x coordinate")
        ax.set_ylabel("Thermal-array y coordinate")

        ax.set_xlim(-0.5, thermal_w - 0.5)
        ax.set_ylim(thermal_h - 0.5, -0.5)

        plt.tight_layout()
        plt.show()
        plt.close(fig)

        action = (
            input(
                "\nConfirm this thermal line? "
                "Enter 'c' to confirm, 'r' to redo, "
                "or 'q' to quit: "
            )
            .strip()
            .lower()
        )

        if action == "c":
            print("\nThermal-array line confirmed.")
            return line_definition

        if action == "q":
            print("\nQuitting without saving thermal coordinates.")
            return None

        print("\nRedoing thermal-line selection.")
