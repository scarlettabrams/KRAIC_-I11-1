# Flow Speed Monitor v2

Measure gas and solution slug lengths and nominal flow rate from a horizontal, left-to-right flow image. The module supports both live UVC capture and recorded videos. It uses fixed viewport calibration, a narrow contrast strip, subpixel threshold crossings, and persistent slug IDs.

**Updated dashboard preview:** `Development/Test_Results/dashboard_update_20261020/tracking_review.mp4`. The original review remains at `Development/Test_Results/tracking_review.mp4`. Blue denotes gas, green denotes solution, and amber denotes a partial or excluded segment. The video includes the original image, enlarged viewport, enlarged measurement strip, IDs, instantaneous lengths, and the intensity profile/threshold. Length labels on the strip are current frame estimates; the exported result for an accepted track is the median of its complete observations.

## Files

| File | Purpose |
|---|---|
| `flowspeedmonitor_v2.py` | Camera/video input, calibration, image analysis, tracking, export, overlay and command-line entry points. |
| `flowspeedmonitor_v2_config.json` | Editable camera, geometry and analysis settings; saved calibration for each resolution. |
| `flowspeedmonitor_v2_menu.py` | Equipment-specific entry point for the existing shared equipment console. |
| `requirements.txt` | Python dependencies. |
| `Development/EQUIPMENT_CLI/` | Existing shared console implementation; retained and imported rather than duplicated. |
| `Development/FSM_v2_SPEC.md` | Requirements and implementation/validation decisions (§7). |
| `Development/Test_Video/` | Original recording and its metadata/timestamp sidecars. |
| `Development/Test_Results/` | Annotated MP4, preview images, individual-track CSV, per-frame diagnostics, JSON report and test notes. |
| `tests/test_flowspeedmonitor_v2.py` | Offline regression tests with analytic synthetic lengths/counts, failures and timestamp checks. |
| `tests/check_video_resolutions.py` | Repeatable comparison with software-resampled 1920×1080 frames. |

## Installation and first use

Use Python 3.10 or later. From this `Software` folder:

```sh
python3 -m pip install -r requirements.txt
python3 flowspeedmonitor_v2_menu.py
```

The console supports:

- `calibrate`: sample passing live flow, detect viewport and strip, calibrate threshold, display geometry for review, then save it. In the review window, press `v` to draw the full physical viewport or `r` to draw the active ROI. Press Enter to accept or Esc to cancel. The selection previews are fitted to the screen and converted back to source coordinates.
- `slugs`: collect 10 seconds and return separate gas/solution mean and median lengths in mm, accepted counts and rejected/incomplete counts/reasons.
- `flow`: collect 2 seconds and return mean nominal flow in mL/min, valid/invalid speed sample counts, achieved frame rate, negotiated camera mode and tube diameter.
- `live`: open the review-style live interface with the camera, highlighted ROI, blue gas/green solution detection, individual segment lengths and intensity profile/threshold. Large readouts show 10-second rolling means for speed (mm/s), estimated flow (mL/min), and unique accepted gas/solution lengths (mm), with corresponding length histograms. Missing measurements show `--`; partial/out-of-range tracks do not enter length means. Press Q, Esc, close the window or Ctrl+C to return to the console. Requires reviewed calibration for the actual camera resolution. No measurements are exported by this view.
- `help`, `quit`: supplied by the shared equipment console. Camera connections are scoped to each action and released on completion/errors.

Choose the correct camera `device` and tube internal diameter in the JSON first. Camera index 0 is an editable starting setting, not proof that it selects the intended camera. Default live request is **1920×1080 at 30 fps, MJPEG**. A mismatched negotiated resolution is an error. Driver-reported and achieved fps are reported separately; achieved fps is measured from frame-read times. `focus_absolute` is optional and backend-specific; leave it null unless its units/value are known and verify focus in the image. Failure to apply an explicitly requested focus lock raises an error.

There is deliberately **no live 1920×1080 calibration prefilled**. Calibrate the actual setup before collection. The saved 3264×2448 calibration is for the supplied test recording only. Do not use software-resampled geometry as a live camera calibration.

## Reproduce the supplied recording test

```sh
python3 flowspeedmonitor_v2.py replay Development/Test_Video/flow_20261019_120739_859496.avi --output Development/Test_Results
```

The matching `.timestamps.csv` is discovered beside the video. The parser requires contiguous frame IDs starting at zero, strictly increasing finite elapsed times, and exactly one timestamp per decoded frame. `--timestamps PATH` supplies another sidecar. The recording's old absolute paths inside its metadata are not used to locate the video or timestamps.

Use `--no-render` for CSV/JSON analysis only or `--duration 10` for a shorter replay. Replay processes the original source frames at their actual timestamp values. The review MP4 uses a constant 30 fps presentation timeline, holding the preceding source image until the next timestamp. It does not invent higher-frame-rate camera observations. H.264 encoding support in the OpenCV installation is required to render this MP4; if unavailable, the function raises a clear error and analysis can run with `--no-render`.

For a different recording, calibrate its own resolution first:

```sh
python3 flowspeedmonitor_v2.py calibrate-video PATH_TO_VIDEO --review
```

`--viewport X0 Y0 X1 Y1` and `--roi X0 Y0 X1 Y1` provide known source-pixel geometry. Coordinates are `[x0, y0, x1, y1]`, with end-exclusive bounds; the scale uses the distance between the first and last included pixel centres, matching the recording's original calibration. Recalibration replaces the saved entry for that resolution, so use `--config ANOTHER_JSON` to keep calibrations for different camera positions/setups separate.

## Main functions and classes

All coordinates are in source-frame pixels; lengths are mm, timestamps seconds, linear speeds mm/s and volumetric rates mL/min. Functions return Python objects and do not open a display unless stated.

| Function/class | Inputs and behaviour | Output / side effects |
|---|---|---|
| `load_config(path)` | Load JSON and check core geometry/timing settings. Defaults to the JSON alongside the module, independent of working directory. | Settings dictionary; no camera connection. |
| `save_config(config, path)` | Save settings/calibrations. | Atomically replaces the JSON. |
| `calibrate(frames, config, viewport=None, roi=None, source=...)` | Use at least 3 same-resolution flow frames. Detect the illuminated region, search its top quarter for temporal contrast, exclude fixed margins, then apply the v1-style two-cluster threshold fraction. Optional geometry overrides allow known or manual calibration. | Unsaved calibration dictionary including scale, ROI, threshold, baselines, timestamp, maximum length and source. Automatic geometry still needs visual inspection. |
| `review_calibration(frame, calibration)` | Show fitted preview; adjust viewport and ROI with `v`/`r`, Enter accepts, Esc cancels. | Corrected geometry; opens GUI, does not save by itself. |
| `calibrate_live(config, config_path, duration_s=4)` | Open live camera, sample flow, auto-calibrate, require manual visual review, recalculate threshold from reviewed geometry. | Reviewed calibration; saves configuration and closes camera. |
| `get_calibration(config, frame, calibration=None)` | Require matching resolution and valid geometry/physical scale. | Calibration with current configured ROI-length limit; raises on absent/stale scale. |
| `VideoSource(path, timestamps=None, allow_nominal_timing=False)` | Read original video and aligned timestamps. Use as a context manager. | Iterator of `FramePacket(frame_id, timestamp_s, frame)`; closes video on context exit. Explicit nominal timing opt-in is unsuitable for timing validation. |
| `CameraSource(config)` | Open requested mode; optionally apply configured focus; check negotiated resolution. Use as a context manager. | Same packet interface as video, monotonic frame-read times and negotiated mode. These are not sensor-exposure timestamps. |
| `analyse_frame(frame, config, calibration=None)` | Extract fixed strip, vertically average/smooth it, interpolate threshold crossings. Remove and log only internal phase islands below the requested 0.05 mm minimum. | Profile, phase observations (including partials), contrast validity and ignored-subminimum feature details. No persistent IDs or counts. |
| `slug_size_simple(frame, config, calibration=None)` | Single-frame analysis using the same segmentation. | Complete in-range lengths per phase plus diagnostics. Repeated calls can observe the same slug; use the tracker for unique counts. |
| `estimate_motion(previous, current, dt, config, calibration)` | Bound profile displacement, reject ambiguous periodic matches/reversal, then estimate speed from matched complete gas trailing edges. | Displacement, speed (or None), status. No speed integration is used for slug lengths. |
| `flow_from_speed(speed_mm_s, tube_id_mm)` | Apply circular tube cross-section and unit conversion. | Nominal mL/min; assumes interface speed represents bulk flow. It is not independently verified pump delivery. |
| `SlugTracker(config, calibration)` | Keep one instance for a continuous collection. Call `process(frame, timestamp_s, frame_id)` once per frame, then `finish()` at shutdown. | Frame diagnostics with persistent IDs; `records` contains finalized tracks; `events` contains discontinuities. `finish()` rejects open end partials and is idempotent. |
| `summarize(records)` | Use accepted unique track records, one vote per slug. | Gas/solution count, mean/median and rejected reasons; absent means are None, not zero. |
| `collect_live(config, duration_s=10, callback=None)` | Bounded live collection requiring reviewed calibration. Optional callback receives `(packet, frame_result)` for a GUI. | Summary, records, flow statistics, timing and negotiated mode. Camera closes on completion/error. |
| `draw_tracking(frame, result, calibration, summary=None)` | Render image, phase strip, IDs, lengths and threshold profile. | 1440×900 BGR dashboard image suitable for display or video writing. |
| `replay_video(video, config, output_dir, ...)` | Run the same tracker on recorded frames; optional callbacks, duration and video rendering. | Report dictionary; writes CSV/JSON and optional H.264 MP4/previews. Existing files of the same names in the chosen output folder are replaced. |
| `export_results(output_dir, records, diagnostics, report)` | Persist collected results. | CSV records, CSV frame diagnostics and JSON summary. |
| `cli(config_path)` | Register equipment-specific commands with `Development.EQUIPMENT_CLI.equipment_cli`. | Interactive console; actions delegate to the above functions. |

### Minimal application integration

```python
import flowspeedmonitor_v2 as fsm

config = fsm.load_config()
with fsm.CameraSource(config) as source:
    tracker = None
    for packet in source:
        if tracker is None:
            cal = fsm.get_calibration(config, packet.frame)
            if not cal["reviewed"]:
                raise ValueError("Review camera calibration first.")
            tracker = fsm.SlugTracker(config, cal)
        result = tracker.process(packet.frame, packet.timestamp_s, packet.frame_id)
        # Send result to the application's UI; consume new entries in tracker.records.
        # Break when the application's stop event is set.
        if packet.timestamp_s >= 10:
            break
    tracker.finish()
    summary = fsm.summarize(tracker.records)
```

For an actual application, own acquisition in a worker thread and pass frames/results to the UI through its normal thread-safe signalling mechanism. The core module has no dependency on a specific GUI framework. `collect_live` and `replay_video` provide bounded synchronous wrappers; callback execution time counts toward processing load.

## Configuration and counting rules

- `geometry.viewport_width_mm` is the **full physical viewport**, nominally 20 mm. Trimming the active ROI does not change mm/pixel. Changing the physical width invalidates saved scale and requires recalibration.
- The test recording uses its metadata's full-width horizontal coordinates `854:2385`, preserving **0.0130719 mm/px**. The vertical viewport bounds were inspected from the images; strip/threshold selection is automatic over 40 frames. With 8% inward margins at each side, its active ROI is **16.8105 mm**, giving a maximum supported length of **13.4484 mm**.
- `geometry.edge_margin_fraction`, `strip_height_fraction` and `search_top_fraction` affect the next calibration. The strip is chosen from temporal phase variation rather than a single dark frame. The first instantaneous threshold crossing never defines the ROI.
- Threshold remains fixed for a session. `analysis.threshold_fraction` retains the two-thirds dark-to-bright baseline placement; the supplied replay threshold is approximately **238.97**. Edge-padded smoothing avoids the artificial dark ends caused by zero-padded averaging.
- `analysis.minimum_slug_mm` is **0.1 mm**, the requested minimum. Internal subminimum islands are logged in frame diagnostics before merging with their surrounding phase, so transient below-range features cannot create extra track IDs. This is an explicit signal-processing decision, not proof that every 0.05 mm slug is detectable.
- Maximum accepted length is `maximum_roi_fraction × active_width_mm`, default **80%**. No speed integration estimates over-ROI lengths.
- A unique track is accepted only after observed upstream entry, at least **two complete observations**, in-range lengths and observed downstream exit. Its reported length is the median of complete observations. Startup/orphan tracks and open collection-end tracks are excluded explicitly.
- A 10 s collection includes only tracks whose entry and exit are both observed inside that window. This prevents partial-window tracks contributing guessed lengths, but fewer tracks may qualify, particularly for long slugs/slow flow. Rejected/incomplete counts are always reported.
- Default frame-gap threshold is **0.15 s**. A gap, low contrast, reversal or identity ambiguity rejects open tracks and restarts identity tracking. New orphan tracks cannot subsequently become accepted simply by reappearing. This conservative policy can reject otherwise measurable physical slugs; see test limitations below.
- The configured 2–10 mL/min range is the intended operating range, not a validated accuracy envelope. Motion search permits up to 15 mL/min to allow margin and flag a search-limit failure rather than silently choose a wrong repeat pattern. Tube diameter must match the apparatus.
- Requested length-error limit is **±max(0.01 mm, 5% of reference length)**. It needs independent references; per-track min/max spread is reported to expose variation, not to replace accuracy validation.

## Tests and current limits

```sh
python3 -B -m unittest discover -s tests -v
python3 tests/check_video_resolutions.py Development/Test_Video/flow_20261019_120739_859496.avi --output Development/Test_Results/resolution_check.json
```

See `Development/Test_Results/TEST_REPORT.md` for the measured replay results and remaining validation. The supplied approximately 60 s video contains **887 frames** and actual timestamp gaps; it is not a uniform 15 fps sensor stream. Its original timing is preserved during analysis.

**This implementation has not demonstrated zero missed/duplicate physical slugs or the provisional length-error limit.** The supplied video has no independent reference lengths/exhaustive manual identity labels. The regression tests check analytic software cases; the annotated recording is for visual review. A timestamp gap and one later association ambiguity cause explicit rejected tracks in this recording. The 0.05 mm minimum is only about **3.83 source pixels**, or **2.25 pixels** in the software-resampled lower-resolution example; reliable physical accuracy there is unverified. Real live 30 fps capture, sustained full-pipeline speed and coverage across 2–10 mL/min require camera/flow testing.

### Live interface

From the equipment console enter `live`, or run `python3 flowspeedmonitor_v2.py live` directly. Use `python3 flowspeedmonitor_v2.py --config PATH live` for another configuration. Camera acquisition, segmentation and tracking use the same path as replay. The displayed flow is nominal interface-speed × tube cross-section, not independently measured pump delivery or individual phase flow. Visible means are frame measurements, not unique accepted-track collection averages.

## Focus-control troubleshooting

If calibration reports that the camera backend could not apply focus lock, OpenCV has rejected a focus-control request; this does not establish that the camera lacks manual focus. The Mac configuration uses the existing `uvc-util` executable at `camera.focus_utility`, with `focus_backend: "uvc-util"`, `focus_device_index: 0`, and the requested `focus_absolute: 798`. This path comes from the earlier camera implementation and is not a Python dependency. The UVC device index is independent of OpenCV camera numbering; verify it identifies the same camera.

`configure_focus(camera, settings)` disables autofocus, reads it back, sets the requested focus, then reads back the value. Each utility invocation has a 5-second timeout. Errors or mismatches stop calibration and release capture. `focus_backend: "opencv"` uses OpenCV controls with readback instead. `focus_absolute: null` leaves focus unchanged and skips both backends; it does not disable autofocus. Confirm image sharpness during calibration review. Utility readback verifies control values, not optical sharpness or camera identity. Focus tests use mocks and do not run the utility or open the camera.

## Live dashboard and calibration update (20 October 2026)

The top-left stream now includes the physical viewport, fixed ROI and blue/green phase overlays. Large cards show trailing **10-second** means for speed (mm/s), nominal flow (mL/min), gas length and solution length (mm), each with a sample count. The two histograms use the gas/solution unique accepted tracks finalized during the same trailing 10-second window, with fixed bins from zero to the supported maximum length. Each track contributes its median complete-frame length once, regardless of how many frames it appears in. Speed and flow are arithmetic means of valid frame estimates; invalid readings are not filled. Empty windows show `--` and empty histograms. During startup, the window contains only the available history. The CLI `flow` measurement remains a separate 2-second collection.

The bottom enlarged phase strip, IDs/length labels and aligned light-intensity profile/threshold are retained. The display refreshes at up to 10 Hz while every acquired frame is still analysed. Completed records are consumed once by bounded rolling buffers before the live history is cleared.

Calibration samples across the requested duration and retains at most 24 grayscale frames (about 50 MB at 1920×1080) instead of 60 colour frames (about 373 MB). Full-image medians use row blocks to bound temporary allocation and are skipped altogether when geometry is supplied after review. The preview closes only its own window and pumps the final close event.

Automatic right-edge refinement uses a connected dimmer contour, bounded to an outward extension of 5% of detected viewport width. `geometry.right_edge_brightness_ratio`, default 0.8, multiplies the initial viewport intensity cutoff for this right-edge search. This heuristic aims to include the dim rim; it still requires visual confirmation of the physical edge. In calibration review, `+` (or `=`) extends the right edge by one source pixel; `-` retracts it. `v` still allows a full manual viewport selection and `r` adjusts the active ROI. These changes affect new calibrations only: existing saved geometry is preserved. Recalibrate to apply the refined detector.

The lag/crash investigation identified excessive frame retention and repeated median work, but no Python/native crash log was supplied. Offline timing, window lifecycle tests and rendering checks do not establish that the original crash has been reproduced or eliminated on live hardware.
