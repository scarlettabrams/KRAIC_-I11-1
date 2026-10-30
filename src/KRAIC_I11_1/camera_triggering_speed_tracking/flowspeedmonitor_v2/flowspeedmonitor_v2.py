"""V2 camera acquisition, calibration, threshold segmentation and unique slug tracking.

Only numpy and opencv-python are required. See README.md for units, calibration,
track acceptance rules and the distinction between replay checks and validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import tempfile
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

DEFAULT_CONFIG_PATH = Path(__file__).with_name("flowspeedmonitor_v2_config.json")


def load_config(path=DEFAULT_CONFIG_PATH) -> dict:
    """Load settings; reject invalid physical scales, limits and camera dimensions."""
    c = json.loads(Path(path).read_text())
    g, a = c["geometry"], c["analysis"]
    for value in (
        g["viewport_width_mm"],
        g["tube_id_mm"],
        a["minimum_slug_mm"],
        a["max_frame_gap_s"],
        a["match_tolerance_mm"],
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "Physical scales and timing/tolerance settings must be positive."
            )
    if not 0 < a["maximum_roi_fraction"] < 1 or not 0 < a["threshold_fraction"] < 1:
        raise ValueError("ROI and threshold fractions must lie between zero and one.")
    if not 0 < g.get("right_edge_brightness_ratio", 0.8) <= 1:
        raise ValueError("right_edge_brightness_ratio must lie between zero and one.")
    if (
        not 0 <= g["edge_margin_fraction"] < 0.25
        or not 0 < g["search_top_fraction"] <= 1
    ):
        raise ValueError("Invalid calibration search settings.")
    if any(c["camera"][k] <= 0 for k in ("width_px", "height_px", "target_fps")):
        raise ValueError("Invalid camera mode.")
    return c


def save_config(config: dict, path=DEFAULT_CONFIG_PATH) -> None:
    """Atomically save configuration, including resolution-specific calibrations."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
            temporary = f.name
            json.dump(config, f, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def flow_from_speed(speed_mm_s: float, tube_id_mm: float) -> float:
    """Convert linear interface speed to nominal mL/min using tube cross-section."""
    return speed_mm_s * math.pi * (tube_id_mm / 2) ** 2 * 60 / 1000


def _gray(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame


def _smooth(profile, window):
    window = max(1, int(window) | 1)
    if window == 1:
        return np.asarray(profile, dtype=float)
    return np.convolve(
        np.pad(profile, window // 2, mode="edge"),
        np.ones(window) / window,
        mode="valid",
    )


def _baselines(values, minimum_contrast=12):
    values = np.asarray(values, dtype=float).ravel()
    if len(values) < 10 or not np.isfinite(values).all():
        raise ValueError("Insufficient finite intensity samples.")
    centres = np.percentile(values, [10, 90])
    for _ in range(30):
        labels = abs(values[:, None] - centres).argmin(axis=1)
        if min(np.bincount(labels, minlength=2)) < max(3, len(values) * 0.005):
            raise ValueError("Both phases must be visible during calibration.")
        new = np.array([values[labels == i].mean() for i in range(2)])
        if np.max(abs(new - centres)) < 0.01:
            break
        centres = new
    low, high = sorted(float(v) for v in centres)
    if high - low < minimum_contrast:
        raise ValueError("Insufficient gas/solution contrast.")
    return low, high


def calibrate(
    frames: list[np.ndarray],
    config: dict,
    *,
    viewport=None,
    roi=None,
    source="automatic",
) -> dict:
    """Select a fixed viewport/strip from multiple flow frames.

    Returns an unsaved calibration.

    Optional viewport and ROI are [x0,y0,x1,y1] in this resolution, end-exclusive.
    They allow recorded physical calibration or manually inspected corrections.
    """
    if len(frames) < 3:
        raise ValueError("At least three calibration frames are required.")
    h, w = frames[0].shape[:2]
    if any(f.shape[:2] != (h, w) for f in frames):
        raise ValueError("Calibration frames have different resolutions.")
    gray = np.stack([_gray(f) for f in frames])
    g, a = config["geometry"], config["analysis"]
    if viewport is None:
        # Row blocks bound median temporary allocations; no full float stack.
        median = np.empty((h, w), dtype=np.uint8)
        for row in range(0, h, 32):
            median[row : row + 32] = np.median(gray[:, row : row + 32], axis=0).astype(
                np.uint8
            )
        level = float(np.percentile(median, 99.5)) * g["viewport_brightness_fraction"]
        mask = (median > level).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        candidates = [
            s
            for s in stats[1:]
            if s[2] > w * 0.15
            and s[3] > h * 0.02
            and s[2] > s[3] * 1.5
            and s[4] > w * h * 0.01
        ]
        if not candidates:
            raise ValueError(
                "No sufficiently large illuminated horizontal viewport found."
            )
        candidates.sort(key=lambda s: int(s[4]), reverse=True)
        if len(candidates) > 1 and candidates[1][4] > 0.8 * candidates[0][4]:
            raise ValueError("Ambiguous illuminated viewport; use manual calibration.")
        x, y, vw, vh, _ = map(int, candidates[0])
        # Dim right rim may fall outside the main bright component. Refine only
        # within a bounded extension, using the connected lower-brightness region.
        lower = (median > level * g.get("right_edge_brightness_ratio", 0.8)).astype(
            np.uint8
        )
        _, lower_labels, lower_stats, _ = cv2.connectedComponentsWithStats(lower)
        seed_label = lower_labels[y + vh // 2, x + vw // 2]
        right = x + vw
        if seed_label:
            lx, ly, lw, lh, _ = map(int, lower_stats[seed_label])
            right = max(right, min(lx + lw, right + round(vw * 0.05)))
        viewport = [x, y, right, y + vh]
    x0, y0, x1, y1 = map(int, viewport)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError("Viewport lies outside image.")
    if roi is None:
        margin = round((x1 - x0) * g["edge_margin_fraction"])
        left, right = x0 + margin, x1 - margin
        sh = max(3, round(h * g["strip_height_fraction"]))
        last = min(y1 - sh, y0 + round((y1 - y0) * g["search_top_fraction"]) - sh)
        best = None
        for y in range(y0, last + 1, max(1, sh // 4)):
            profiles = gray[:, y : y + sh, left:right].mean(axis=1)
            # Fixed spatial stains have no temporal variation; passing interfaces do.
            score = float(np.mean(np.std(profiles, axis=0)))
            if best is None or score > best[0]:
                best = (score, y)
        if best is None or best[0] < 1:
            raise ValueError("No moving phase-contrast strip found in top quarter.")
        roi = [left, best[1], right, best[1] + sh]
    rx0, ry0, rx1, ry1 = map(int, roi)
    if not (x0 <= rx0 < rx1 <= x1 and y0 <= ry0 < ry1 <= y1):
        raise ValueError("Active ROI must lie within the viewport.")
    profiles = gray[:, ry0:ry1, rx0:rx1].mean(axis=1)
    low, high = _baselines(profiles, a["minimum_contrast"])
    scale = g["viewport_width_mm"] / (x1 - x0 - 1)
    active = (rx1 - rx0 - 1) * scale
    return {
        "resolution": [w, h],
        "viewport": list(map(int, viewport)),
        "roi": list(map(int, roi)),
        "mm_per_pixel": scale,
        "active_width_mm": active,
        "maximum_slug_mm": active * a["maximum_roi_fraction"],
        "intensity_threshold": low + a["threshold_fraction"] * (high - low),
        "low_baseline": low,
        "high_baseline": high,
        "source": source,
        "calibrated_at": datetime.now(UTC).isoformat(),
        "reviewed": False,
        "calibration_frame_count": len(frames),
    }


def get_calibration(config, frame, calibration=None):
    """Require matching resolution and valid, internally consistent geometry."""
    h, w = frame.shape[:2]
    cal = calibration or config["calibrations"].get(f"{w}x{h}")
    if cal is None or cal["resolution"] != [w, h]:
        raise ValueError(f"No matching {w}x{h} calibration. Run calibration first.")
    x0, y0, x1, y1 = cal["viewport"]
    left_edge, t, r, b = cal["roi"]
    if not (0 <= x0 <= left_edge < r <= x1 <= w and 0 <= y0 <= t < b <= y1 <= h):
        raise ValueError("Invalid saved viewport/ROI.")
    expected = config["geometry"]["viewport_width_mm"] / (x1 - x0 - 1)
    if not math.isclose(expected, cal["mm_per_pixel"], rel_tol=1e-8):
        raise ValueError("Physical width changed; recalibrate before measurement.")
    cal = dict(cal)
    cal["active_width_mm"] = (r - left_edge - 1) * expected
    cal["maximum_slug_mm"] = (
        cal["active_width_mm"] * config["analysis"]["maximum_roi_fraction"]
    )
    if config["analysis"]["minimum_slug_mm"] >= cal["maximum_slug_mm"]:
        raise ValueError("Minimum supported length exceeds the calibrated maximum.")
    return cal


@dataclass
class FramePacket:
    frame_id: int
    timestamp_s: float
    frame: np.ndarray


class VideoSource:
    """Decode every video frame with strict CSV frame_ID/elapsed_s alignment.

    Missing/extra/nonmonotonic timestamps are errors. Without a sidecar, explicit
    allow_nominal_timing=True is required; this is unsuitable for timing validation.
    """

    def __init__(self, path, timestamps=None, *, allow_nominal_timing=False):
        self.path = Path(path)
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise OSError(f"Cannot open video: {path}")
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        self.times = None
        sidecar = (
            Path(timestamps) if timestamps else self.path.with_suffix(".timestamps.csv")
        )
        try:
            if sidecar.exists():
                with sidecar.open() as f:
                    rows = list(csv.DictReader(f))
                ids = [int(r["frame_ID"]) for r in rows]
                self.times = [float(r["elapsed_s"]) for r in rows]
                if (
                    ids != list(range(len(rows)))
                    or not self.times
                    or not np.isfinite(self.times).all()
                ):
                    raise ValueError(
                        "Timestamp IDs must be contiguous from 0, with finite "
                        "elapsed_s."
                    )
                if any(
                    b <= a for a, b in zip(self.times, self.times[1:], strict=False)
                ):
                    raise ValueError("Frame timestamps must increase strictly.")
            elif not allow_nominal_timing or self.fps <= 0:
                raise ValueError(
                    "Timestamp sidecar required; explicitly opt in to nominal playback "
                    "timing."
                )
        except Exception:
            self.cap.release()
            raise
        self.timing_source = (
            "sidecar elapsed_s" if self.times is not None else "nominal playback fps"
        )

    def __iter__(self) -> Iterator[FramePacket]:
        i = 0
        while True:
            ok, frame = self.cap.read()
            if not ok:
                break
            if self.times is not None and i >= len(self.times):
                raise ValueError("Video has more frames than timestamps.")
            yield FramePacket(
                i, self.times[i] if self.times is not None else i / self.fps, frame
            )
            i += 1
        if self.times is not None and i != len(self.times):
            raise ValueError(
                f"Decoded {i} frames but sidecar contains {len(self.times)} timestamps."
            )

    def close(self):
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def configure_focus(camera, settings):
    """Apply an explicitly configured focus lock and verify its readback.

    uvc-util controls are used only when selected in configuration; its device
    index is independent of OpenCV's camera index. No hardware is opened here.
    """
    value = settings.get("focus_absolute")
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            "camera.focus_absolute must be a finite nonnegative number or null."
        )
    backend = settings.get("focus_backend", "opencv")
    if backend == "opencv":
        if not camera.set(cv2.CAP_PROP_AUTOFOCUS, 0):
            raise OSError(
                'OpenCV cannot disable autofocus. Configure focus_backend="uvc-util" '
                "on the Mac with the correct utility/device, or use "
                "focus_absolute=null to leave focus unchanged."
            )
        if not camera.set(cv2.CAP_PROP_FOCUS, value):
            raise OSError(
                f"OpenCV cannot set focus_absolute={value:g}. Use a supported focus "
                "backend."
            )
        auto = camera.get(cv2.CAP_PROP_AUTOFOCUS)
        actual = camera.get(cv2.CAP_PROP_FOCUS)
        if (
            not math.isfinite(auto)
            or auto != 0
            or not math.isfinite(actual)
            or not math.isclose(actual, value, abs_tol=0.5, rel_tol=0)
        ):
            raise OSError(
                f"OpenCV focus readback mismatch: autofocus={auto}, focus={actual}; "
                f"requested {value:g}."
            )
    elif backend == "uvc-util":
        utility = settings.get("focus_utility")
        index = settings.get("focus_device_index")
        if not isinstance(utility, str) or not utility:
            raise ValueError("Set camera.focus_utility to the uvc-util executable.")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError(
                "Set camera.focus_device_index to the intended UVC device index."
            )

        def control(*args):
            command = [utility, "-I", str(index), *args]
            try:
                result = subprocess.run(
                    command, check=True, capture_output=True, text=True, timeout=5
                )
            except FileNotFoundError as exc:
                raise OSError(f"UVC focus utility not found: {utility}") from exc
            except subprocess.TimeoutExpired as exc:
                raise OSError(
                    "UVC focus control timed out after 5 s; check the utility and "
                    "selected camera."
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise OSError(
                    "UVC focus command failed: "
                    f"{(exc.stderr or exc.stdout or str(exc)).strip()}"
                ) from exc
            if "ERROR:" in result.stdout or "ERROR:" in result.stderr:
                raise OSError(
                    "UVC focus command failed: "
                    f"{(result.stderr or result.stdout).strip()}"
                )
            return result.stdout.strip()

        control("-s", "auto-focus=0")
        auto_text = control("-o", "auto-focus").lower()
        if auto_text not in ("0", "false"):
            raise OSError(
                f"UVC autofocus did not read back as disabled: {auto_text!r}."
            )
        control("-s", f"focus-abs={value:g}")
        focus_text = control("-o", "focus-abs")
        try:
            actual = float(focus_text)
        except ValueError as exc:
            raise OSError(f"Invalid UVC focus readback: {focus_text!r}.") from exc
        if not math.isfinite(actual) or not math.isclose(
            actual, value, abs_tol=0.5, rel_tol=0
        ):
            raise OSError(
                f"UVC focus readback mismatch: requested {value:g}, received "
                f"{focus_text!r}."
            )
    else:
        raise ValueError(
            f"Unknown camera.focus_backend: {backend!r}. Use opencv or uvc-util."
        )
    return {
        "backend": backend,
        "autofocus": False,
        "focus_absolute": actual,
        "verified": True,
    }


class CameraSource:
    """Request the configured UVC mode; expose negotiated mode and read timestamps."""

    def __init__(self, config):
        c = config["camera"]
        self.cap = cv2.VideoCapture(c["device"])
        try:
            if not self.cap.isOpened():
                raise OSError("Cannot open configured camera.")
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*c["fourcc"]))
            for prop, key in [
                (cv2.CAP_PROP_FRAME_WIDTH, "width_px"),
                (cv2.CAP_PROP_FRAME_HEIGHT, "height_px"),
                (cv2.CAP_PROP_FPS, "target_fps"),
            ]:
                self.cap.set(prop, c[key])
            self.focus_status = configure_focus(self.cap, c)
            self.negotiated = {
                "width_px": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height_px": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "reported_fps": float(self.cap.get(cv2.CAP_PROP_FPS)),
            }
            if [self.negotiated["width_px"], self.negotiated["height_px"]] != [
                c["width_px"],
                c["height_px"],
            ]:
                raise OSError(
                    f"Camera did not negotiate requested resolution: {self.negotiated}"
                )
        except Exception:
            self.cap.release()
            raise
        self.timing_source = "monotonic time immediately after frame read"

    def __iter__(self):
        start = time.monotonic()
        i = 0
        while True:
            ok, frame = self.cap.read()
            ts = time.monotonic() - start
            if not ok:
                raise OSError("Camera frame read failed.")
            yield FramePacket(i, ts, frame)
            i += 1

    def close(self):
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@dataclass
class Observation:
    phase: str
    left_px: float
    right_px: float
    left_clipped: bool
    right_clipped: bool
    length_mm: float | None
    track_id: int | None = None
    status: str = "partial"

    @property
    def complete(self):
        return not self.left_clipped and not self.right_clipped


def analyse_frame(frame, config, calibration=None) -> dict:
    """Return smoothed profile and subpixel gas/solution runs, including partials."""
    cal = get_calibration(config, frame, calibration)
    left_edge, t, r, b = cal["roi"]
    profile = _smooth(
        _gray(frame[t:b, left_edge:r]).mean(axis=0),
        config["analysis"]["smoothing_window_px"],
    )
    threshold = cal["intensity_threshold"]
    gas = profile < threshold
    ignored_features = []
    # Remove only internal islands strictly below the declared supported minimum.
    # Log them explicitly: a subminimum flicker must not split a real track into IDs.
    while True:
        changes = np.flatnonzero(gas[1:] != gas[:-1]) + 1
        removed = False
        for start, end in zip(changes[:-1], changes[1:], strict=False):
            left = (
                start
                - 1
                + (threshold - profile[start - 1])
                / (profile[start] - profile[start - 1])
            )
            right = (
                end
                - 1
                + (threshold - profile[end - 1]) / (profile[end] - profile[end - 1])
            )
            length = (right - left) * cal["mm_per_pixel"]
            if length < config["analysis"]["minimum_slug_mm"]:
                ignored_features.append(
                    {
                        "phase": "gas" if gas[start] else "solution",
                        "length_mm": float(length),
                        "left_px": float(left),
                    }
                )
                gas[start:end] = gas[start - 1]
                removed = True
                break
        if not removed:
            break
    changes = np.flatnonzero(gas[1:] != gas[:-1]) + 1
    edges = (
        [0.0]
        + [
            float(i - 1 + (threshold - profile[i - 1]) / (profile[i] - profile[i - 1]))
            for i in changes
        ]
        + [float(len(profile) - 1)]
    )
    starts = [0] + changes.tolist()
    observations = []
    for i, (left, right) in enumerate(zip(edges[:-1], edges[1:], strict=False)):
        complete = i > 0 and i < len(edges) - 2
        observations.append(
            Observation(
                "gas" if gas[starts[i]] else "solution",
                left,
                right,
                i == 0,
                i == len(edges) - 2,
                (right - left) * cal["mm_per_pixel"] if complete else None,
            )
        )
    # A long single phase is allowed visually but cannot supply reliable motion/length.
    contrast = float(np.partition(profile, -2)[-2] - np.partition(profile, 1)[1])
    return {
        "profile": profile,
        "observations": observations,
        "contrast": contrast,
        "ignored_subminimum_features": ignored_features,
        "valid": (
            contrast >= config["analysis"]["minimum_contrast"]
            and np.count_nonzero(gas) >= 2
            and np.count_nonzero(~gas) >= 2
        ),
    }


def slug_size_simple(frame, config, calibration=None) -> dict:
    """Measure complete in-range runs in one frame; does not count unique slugs."""
    cal = get_calibration(config, frame, calibration)
    result = analyse_frame(frame, config, cal)
    result["lengths_mm"] = {
        phase: [
            o.length_mm
            for o in result["observations"]
            if o.phase == phase
            and o.complete
            and result["valid"]
            and config["analysis"]["minimum_slug_mm"]
            <= o.length_mm
            <= cal["maximum_slug_mm"]
        ]
        for phase in ("gas", "solution")
    }
    return result


def estimate_motion(previous, current, dt, config, calibration):
    """Estimate bounded profile displacement, then speed.

    Speed comes from matched gas trailing edges.

    Correlation detects periodic ambiguity; a nonunique match invalidates tracking.
    Negative motion is reported as reversal. No speed integration measures lengths.
    """
    a = config["analysis"]
    scale = calibration["mm_per_pixel"]
    area = math.pi * (config["geometry"]["tube_id_mm"] / 2) ** 2
    vmax = a["motion_search_max_ml_min"] * 1000 / 60 / area
    max_shift = min(len(current["profile"]) // 3, max(2, math.ceil(vmax * dt / scale)))
    p, q = previous["profile"], current["profile"]
    scores = []
    for shift in range(-max_shift, max_shift + 1):
        left = p[max(0, -shift) : min(len(p), len(p) - shift)]
        right = q[max(0, shift) : min(len(q), len(q) + shift)]
        left, right = left - left.mean(), right - right.mean()
        denom = float(np.linalg.norm(left) * np.linalg.norm(right))
        scores.append(float(np.dot(left, right) / denom) if denom > 0 else -1)
    best = int(np.argmax(scores))
    displacement = best - max_shift
    exclusion = max(4, round(a["match_tolerance_mm"] / scale))
    competitors = [s for i, s in enumerate(scores) if abs(i - best) > exclusion]
    if scores[best] < a["minimum_motion_correlation"]:
        return None, None, "poor_motion_correlation"
    if (
        competitors
        and scores[best] - max(competitors) < a["ambiguity_correlation_margin"]
    ):
        return None, None, "ambiguous_motion"
    if abs(displacement) >= max_shift - 1:
        return None, None, "motion_search_limit"
    if displacement < -2:
        return None, None, "reversed_flow"
    # Trailing edge for left-to-right motion is the left boundary of each gas run.
    # Use complete gas runs, and gate matches by the profile displacement estimate.
    p_edges = [
        o.left_px for o in previous["observations"] if o.phase == "gas" and o.complete
    ]
    q_edges = [
        o.left_px for o in current["observations"] if o.phase == "gas" and o.complete
    ]
    speeds = []
    for edge in p_edges:
        candidates = [
            e - edge for e in q_edges if abs(e - edge - displacement) <= exclusion
        ]
        if len(candidates) == 1:
            speeds.append(candidates[0] * scale / dt)
    speed = float(np.median(speeds)) if speeds else None
    if speed is not None and speed < 0:
        speed = 0.0 if abs(displacement) <= 2 else None
    return (
        float(max(0, displacement)),
        speed,
        "ok" if displacement > 2 else "stationary",
    )


@dataclass
class Track:
    track_id: int
    phase: str
    first_s: float
    last_s: float
    observation: Observation
    entered: bool
    lengths: list[float] = field(default_factory=list)
    sample_times: list[float] = field(default_factory=list)


class SlugTracker:
    """Maintain phase IDs and finalize each track once, only after observed exit.

    Require observed entry, >=2 complete observations, supported length, and clean
    matching throughout. Reset events reject open tracks and suppress orphan counts.
    """

    def __init__(self, config, calibration):
        self.config, self.cal = config, calibration
        self.active: dict[int, Track] = {}
        self.records = []
        self.next_id = 1
        self.previous = None
        self.previous_s = None
        self.frame_count = 0
        self.events = []

    def _finish(self, track, reason, timestamp):
        a = self.config["analysis"]
        length = float(np.median(track.lengths)) if track.lengths else None
        if reason == "exited":
            if not track.entered:
                reason = "startup_or_orphan_partial"
            elif len(track.lengths) < a["minimum_complete_observations"]:
                reason = "insufficient_complete_observations"
            elif not a["minimum_slug_mm"] <= length <= self.cal["maximum_slug_mm"]:
                reason = "length_out_of_range"
            elif any(v > self.cal["maximum_slug_mm"] for v in track.lengths):
                reason = "inconsistent_out_of_range_length"
            else:
                reason = "accepted"
        self.records.append(
            {
                "track_id": track.track_id,
                "phase": track.phase,
                "status": reason,
                "length_mm": length,
                "first_seen_s": track.first_s,
                "last_seen_s": track.last_s,
                "finalized_s": timestamp,
                "complete_observations": len(track.lengths),
                "length_min_mm": min(track.lengths) if track.lengths else None,
                "length_max_mm": max(track.lengths) if track.lengths else None,
            }
        )

    def _reset(self, reason, timestamp):
        for track in self.active.values():
            self._finish(track, reason, timestamp)
        self.active.clear()
        self.events.append({"timestamp_s": timestamp, "reason": reason})

    def _new(self, obs, timestamp, entered):
        track = Track(self.next_id, obs.phase, timestamp, timestamp, obs, entered)
        self.next_id += 1
        self._update(track, obs, timestamp)
        self.active[track.track_id] = track

    def _update(self, track, obs, timestamp):
        track.observation, track.last_s = obs, timestamp
        obs.track_id = track.track_id
        if obs.complete:
            track.lengths.append(obs.length_mm)
            track.sample_times.append(timestamp)
            obs.status = (
                "in range"
                if self.config["analysis"]["minimum_slug_mm"]
                <= obs.length_mm
                <= self.cal["maximum_slug_mm"]
                else "OUT OF RANGE"
            )
        else:
            obs.status = "partial"
        if not track.entered:
            obs.status += " / startup-orphan"

    def process(self, frame, timestamp_s, frame_id=None):
        if not math.isfinite(timestamp_s) or (
            self.previous_s is not None and timestamp_s <= self.previous_s
        ):
            raise ValueError(
                "Tracking timestamps must be finite and strictly increasing."
            )
        self.cal = get_calibration(self.config, frame, self.cal)
        result = analyse_frame(frame, self.config, self.cal)
        a = self.config["analysis"]
        displacement, speed, status = None, None, "startup"
        reset = False
        if self.previous_s is not None:
            dt = timestamp_s - self.previous_s
            if dt > a["max_frame_gap_s"]:
                status, reset = "frame_gap", True
            elif (
                not result["valid"]
                or self.previous is None
                or not self.previous["valid"]
            ):
                status, reset = "insufficient_contrast", True
            else:
                displacement, speed, status = estimate_motion(
                    self.previous, result, dt, self.config, self.cal
                )
                reset = displacement is None
        elif not result["valid"]:
            status, reset = "insufficient_contrast", True
        if reset:
            self._reset(status, timestamp_s)
        observations = result["observations"]
        old = dict(self.active)
        matched = set()
        if displacement is not None:
            tol = a["match_tolerance_mm"] / self.cal["mm_per_pixel"]
            proposals = []
            for j, obs in enumerate(observations):
                candidates = []
                for key, tr in old.items():
                    prev = tr.observation
                    if obs.phase != prev.phase:
                        continue
                    errors = []
                    if not prev.left_clipped and not obs.left_clipped:
                        errors.append(abs(obs.left_px - prev.left_px - displacement))
                    if not prev.right_clipped and not obs.right_clipped:
                        errors.append(abs(obs.right_px - prev.right_px - displacement))
                    if errors and max(errors) <= tol:
                        candidates.append((max(errors), key))
                proposals.append((j, candidates))
            # Do not resolve ties by guessing an identity.
            chosen = [(j, cs[0][1]) for j, cs in proposals if len(cs) == 1]
            keys = [key for _, key in chosen]
            if any(len(cs) > 1 for _, cs in proposals) or len(set(keys)) != len(keys):
                self._reset("ambiguous_association", timestamp_s)
                old, chosen, reset, status = {}, [], True, "ambiguous_association"
                speed = None
            for j, key in chosen:
                self._update(self.active[key], observations[j], timestamp_s)
                matched.add(key)
            width = len(result["profile"]) - 1
            for key, tr in old.items():
                if key in matched:
                    continue
                # A track must disappear at the downstream boundary, never in the
                # middle.
                if (
                    tr.observation.right_clipped
                    or tr.observation.left_px + displacement >= width - tol
                ):
                    reason = "exited"
                else:
                    reason = "lost_track"
                self._finish(tr, reason, timestamp_s)
                self.active.pop(key, None)
        for obs in observations:
            if obs.track_id is None:
                # A new slug may become complete between frames, but only close to
                # the upstream edge within this frame's measured displacement.
                entered = (
                    self.previous_s is not None
                    and not reset
                    and displacement is not None
                    and (obs.left_clipped or obs.left_px <= displacement + 2)
                )
                self._new(obs, timestamp_s, entered)
        self.previous, self.previous_s = result, timestamp_s
        self.frame_count += 1
        result.update(
            timestamp_s=timestamp_s,
            frame_id=frame_id,
            motion_status=status,
            speed_mm_s=speed,
            flow_ml_min=flow_from_speed(speed, self.config["geometry"]["tube_id_mm"])
            if speed is not None
            else None,
            displacement_px=displacement,
        )
        return result

    def finish(self):
        """Finalize remaining tracks as collection-end partials; safe to call
        repeatedly.
        """
        for track in self.active.values():
            self._finish(track, "collection_end_partial", self.previous_s)
        self.active.clear()
        return self.records


def summarize(records):
    """Per-phase statistics over unique accepted records; missing means are None."""
    output = {}
    for phase in ("gas", "solution"):
        rows = [r for r in records if r["phase"] == phase]
        accepted = [r["length_mm"] for r in rows if r["status"] == "accepted"]
        reasons = {}
        for r in rows:
            if r["status"] != "accepted":
                reasons[r["status"]] = reasons.get(r["status"], 0) + 1
        output[phase] = {
            "accepted_count": len(accepted),
            "mean_length_mm": float(np.mean(accepted)) if accepted else None,
            "median_length_mm": float(np.median(accepted)) if accepted else None,
            "rejected_or_incomplete_count": len(rows) - len(accepted),
            "reasons": reasons,
        }
    return output


def export_results(output_dir, records, diagnostics, report):
    """Write machine-readable individual tracks, per-frame diagnostics and summary."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in [
        ("slug_measurements.csv", records),
        ("frame_diagnostics.csv", diagnostics),
    ]:
        with (out / name).open("w", newline="") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    (out / "tracking_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )


class RollingMeasurements:
    """Bounded rolling sample means and one median-length value per accepted track.

    Lengths/histograms use tracks finalized within (now-window, now]. Speed and
    flow use valid frame estimates in that interval, without filling invalid gaps.
    """

    def __init__(self, window_s=10):
        self.window_s = float(window_s)
        self.speeds = deque()
        self.lengths = deque()

    def update(self, result, records):
        now = result["timestamp_s"]
        speed, flow = result.get("speed_mm_s"), result.get("flow_ml_min")
        if speed is not None and flow is not None and np.isfinite([speed, flow]).all():
            self.speeds.append((now, speed, flow))
        for r in records:
            if r["status"] == "accepted":
                self.lengths.append((r["finalized_s"], r["phase"], r["length_mm"]))
        cutoff = now - self.window_s
        while self.speeds and self.speeds[0][0] <= cutoff:
            self.speeds.popleft()
        while self.lengths and self.lengths[0][0] <= cutoff:
            self.lengths.popleft()
        return self.snapshot()

    def snapshot(self):
        return {
            "window_s": self.window_s,
            "speed_mm_s": float(np.mean([r[1] for r in self.speeds]))
            if self.speeds
            else None,
            "flow_ml_min": float(np.mean([r[2] for r in self.speeds]))
            if self.speeds
            else None,
            "valid_speed_samples": len(self.speeds),
            "lengths": {
                p: [r[2] for r in self.lengths if r[1] == p]
                for p in ("gas", "solution")
            },
        }


def draw_tracking(
    frame, result, calibration, summary=None, *, live=False, rolling=None
):
    """Readable 1440x900 dashboard: camera/overlay, 10 s metrics and histograms.

    The enlarged phase strip and aligned intensity profile remain at the bottom.
    Supply RollingMeasurements.snapshot() for unique-slug rolling statistics.
    """
    canvas = np.full((900, 1440, 3), (23, 25, 30), np.uint8)
    colors = {"gas": (255, 190, 40), "solution": (90, 220, 100)}
    amber = (0, 190, 255)
    font = cv2.FONT_HERSHEY_SIMPLEX

    def text(s, x, y, color=(235, 235, 235), scale=0.6, thickness=1):
        cv2.putText(canvas, s, (x, y), font, scale, color, thickness, cv2.LINE_AA)

    text("FSM v2 | Gas / Solution tracking", 20, 32, scale=0.85, thickness=2)
    text(
        f"Frame {result['frame_id']}  |  t={result['timestamp_s']:.2f}s  |  "
        f"{result['motion_status']}",
        20,
        62,
        scale=0.65,
    )
    left_edge, t, r, b = calibration["roi"]
    x0, y0, x1, y1 = calibration["viewport"]
    fit = min(610 / frame.shape[1], 280 / frame.shape[0])
    fw, fh = max(1, round(frame.shape[1] * fit)), max(1, round(frame.shape[0] * fit))
    view = cv2.resize(frame, (fw, fh))

    def box_on_view(box, color, width):
        a, c, d, e = [round(v * fit) for v in box]
        cv2.rectangle(view, (a, c), (d, e), color, width)

    # Apply overlays after downscaling so they remain visible on a small stream.
    overlay = view.copy()
    vt, vb = round(t * fit), max(round(t * fit) + 4, round(b * fit))
    for obs in result["observations"]:
        color = colors[obs.phase] if obs.complete and "OUT" not in obs.status else amber
        cv2.rectangle(
            overlay,
            (round((left_edge + obs.left_px) * fit), vt),
            (round((left_edge + obs.right_px) * fit), vb),
            color,
            -1,
        )
    view = cv2.addWeighted(view, 0.45, overlay, 0.55, 0)
    box_on_view(calibration["viewport"], amber, 2)
    box_on_view(calibration["roi"], (255, 255, 255), 1)
    canvas[78 : 78 + fh, 20 : 20 + fw] = view
    text("Viewport: amber | ROI: white | phases: blue / green", 20, 365, scale=0.54)
    if rolling is None:
        rolling = {
            "speed_mm_s": None,
            "flow_ml_min": None,
            "valid_speed_samples": 0,
            "lengths": {"gas": [], "solution": []},
            "window_s": 10,
        }
    values = [
        (
            "Speed",
            rolling["speed_mm_s"],
            "mm/s",
            (235, 235, 235),
            rolling["valid_speed_samples"],
        ),
        (
            "Flow rate",
            rolling["flow_ml_min"],
            "mL/min",
            (235, 235, 235),
            rolling["valid_speed_samples"],
        ),
    ]
    for phase in ("gas", "solution"):
        lengths = rolling["lengths"][phase]
        values.append(
            (
                phase.capitalize() + " length",
                float(np.mean(lengths)) if lengths else None,
                "mm",
                colors[phase],
                len(lengths),
            )
        )
    for i, (label, value, unit, color, n) in enumerate(values):
        cx = 660 + (i % 2) * 380
        cy = 80 + (i // 2) * 140
        cv2.rectangle(canvas, (cx, cy), (cx + 360, cy + 125), (43, 46, 53), -1)
        text(label + " | 10 s mean", cx + 14, cy + 25, color, 0.62)
        text(
            f"{value:.3f}" if value is not None else "--",
            cx + 14,
            cy + 72,
            color,
            1.25,
            2,
        )
        text(unit, cx + 225, cy + 72, color, 0.65)
        text(
            f"n={n} " + ("valid frames" if i < 2 else "unique accepted slugs"),
            cx + 14,
            cy + 108,
            scale=0.5,
        )
    # Two fixed-bin histograms use the same 10 s unique-track population as cards.
    for j, phase in enumerate(("gas", "solution")):
        hx = 45 + j * 710
        hy = 410
        hw = 650
        hh = 85
        samples = rolling["lengths"][phase]
        bins = np.linspace(0, calibration["maximum_slug_mm"], 16)
        counts, _ = np.histogram(samples, bins=bins)
        top = max(1, int(max(counts)))
        text(
            f"{phase.capitalize()} lengths | last 10 s | n={len(samples)}",
            hx,
            hy - 15,
            colors[phase],
            0.62,
        )
        cv2.line(canvas, (hx, hy), (hx, hy + hh), (120, 120, 120), 1)
        cv2.line(canvas, (hx, hy + hh), (hx + hw, hy + hh), (120, 120, 120), 1)
        for k, count in enumerate(counts):
            a = hx + round(k * hw / 15) + 2
            z = hx + round((k + 1) * hw / 15) - 2
            if count:
                cv2.rectangle(
                    canvas,
                    (a, hy + hh - round(count / top * hh)),
                    (z, hy + hh - 1),
                    colors[phase],
                    -1,
                )
        text(str(top), hx - 24, hy + 5, scale=0.42)
        for fraction in (0, 0.5, 1):
            label = f"{calibration['maximum_slug_mm'] * fraction:.1f}"
            text(label, hx + round(hw * fraction) - 10, hy + hh + 20, scale=0.45)
        text("Length (mm)", hx + hw // 2 - 50, hy + hh + 39, scale=0.45)
    strip = frame[max(0, t - 10) : min(frame.shape[0], b + 10), left_edge:r]
    canvas[575:650, 25:1415] = cv2.resize(strip, (1390, 75))
    profile_span = len(result["profile"]) - 1
    for j, obs in enumerate(result["observations"]):
        left = 25 + round(obs.left_px / profile_span * 1390)
        right = 25 + round(obs.right_px / profile_span * 1390)
        color = colors[obs.phase] if obs.complete and "OUT" not in obs.status else amber
        cv2.rectangle(canvas, (left, 575), (right, 650), color, 2)
        label = f"{'G' if obs.phase == 'gas' else 'S'}#{obs.track_id} "
        label += f"{obs.length_mm:.2f} mm" if obs.length_mm is not None else "partial"
        text(
            label,
            min(max(25, (left + right) // 2 - 65), 1230),
            563 if j % 2 == 0 else 676,
            color,
            0.52,
        )
    pts = np.array(
        [
            [25 + round(i / profile_span * 1390), 810 - round(float(v) / 255 * 110)]
            for i, v in enumerate(result["profile"])
        ],
        np.int32,
    )
    cv2.polylines(canvas, [pts], False, (215, 215, 215), 1, cv2.LINE_AA)
    yy = 810 - round(calibration["intensity_threshold"] / 255 * 110)
    cv2.line(canvas, (25, yy), (1415, yy), amber, 1)
    text(
        f"Intensity profile | threshold {calibration['intensity_threshold']:.1f} | ROI "
        f"{calibration['active_width_mm']:.2f} mm",
        25,
        840,
        scale=0.6,
    )
    text(
        "Gas: blue | Solution: green | Partial/out of range: amber", 25, 878, scale=0.54
    )
    text(
        "Q / Esc / close to return"
        if live
        else "Annotated replay | 10 s rolling statistics",
        930,
        878,
        scale=0.54,
    )
    return canvas


def sample_video(path, count=40):
    """Sample calibration frames spread across a video without changing replay
    timing.
    """
    cap = cv2.VideoCapture(str(path))
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not cap.isOpened() or n < 3:
            raise OSError("Cannot sample calibration frames from video.")
        frames = []
        for i in np.linspace(0, n - 1, min(count, n)).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
            ok, frame = cap.read()
            if not ok:
                raise OSError(f"Cannot decode calibration frame {i}.")
            frames.append(frame)
        return frames
    finally:
        cap.release()


def review_calibration(frame, calibration):
    """Inspect/adjust viewport and ROI with fitted previews; Enter accepts, Esc
    cancels.
    """
    cal = dict(calibration)
    h, w = frame.shape[:2]
    factor = min(1, 1200 / w, 800 / h)
    image = cv2.resize(frame, (round(w * factor), round(h * factor)))
    window = (
        "Calibration: v viewport | r ROI | +/- right edge | Enter accept | Esc cancel"
    )
    try:
        while True:
            preview = image.copy()
            for box, color in [
                (cal["viewport"], (0, 220, 255)),
                (cal["roi"], (255, 200, 50)),
            ]:
                x, y, r, b = [round(v * factor) for v in box]
                cv2.rectangle(preview, (x, y), (r, b), color, 2)
            cv2.imshow(window, preview)
            key = cv2.waitKey(30) & 255
            if key in (10, 13):
                return cal["viewport"], cal["roi"]
            if key == 27 or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                raise ValueError("Calibration review cancelled.")
            # +/- adjusts the right viewport edge by one source pixel.
            if key in (ord("+"), ord("="), ord("-")):
                delta = -1 if key == ord("-") else 1
                cal["viewport"][2] = max(
                    cal["viewport"][0] + 2, min(w, cal["viewport"][2] + delta)
                )
            if key in (ord("v"), ord("r")):
                x, y, bw, bh = cv2.selectROI(window, image, False, False)
                if bw > 1 and bh > 1:
                    cal["viewport" if key == ord("v") else "roi"] = [
                        round(v / factor) for v in (x, y, x + bw, y + bh)
                    ]
    finally:
        cv2.destroyWindow(window)
        cv2.waitKey(1)


def replay_video(
    video,
    config,
    output_dir,
    *,
    timestamps=None,
    calibration=None,
    render=True,
    callback: Callable | None = None,
    duration_s=None,
):
    """Track every frame and export CSV/JSON plus optional real-time-paced H.264 MP4.

    Video presentation repeats/omits render frames on a fixed 30 fps timeline;
    analysis always uses each original frame and its actual sidecar timestamp.
    """
    if duration_s is not None and (not math.isfinite(duration_s) or duration_s <= 0):
        raise ValueError("Replay duration must be positive.")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    writer = None
    tracker = None
    cal = None
    diagnostics = []
    times = []
    next_render = 0.0
    start_wall = time.monotonic()
    first_s = None
    last_dashboard = None
    rolling = RollingMeasurements(10)
    record_cursor = 0
    try:
        with VideoSource(video, timestamps) as source:
            for packet in source:
                if first_s is None or tracker is None or cal is None:
                    first_s = packet.timestamp_s
                    cal = get_calibration(config, packet.frame, calibration)
                    tracker = SlugTracker(config, cal)
                    if render:
                        writer = cv2.VideoWriter(
                            str(out / "tracking_review.mp4"),
                            cv2.VideoWriter.fourcc(*"avc1"),
                            30,
                            (1440, 900),
                        )
                        if not writer.isOpened():
                            raise OSError(
                                "H.264 writer unavailable; use --no-render or install "
                                "an H.264-capable OpenCV build."
                            )
                if duration_s is not None and packet.timestamp_s - first_s > duration_s:
                    break
                result = tracker.process(
                    packet.frame, packet.timestamp_s, packet.frame_id
                )
                stats = rolling.update(result, tracker.records[record_cursor:])
                record_cursor = len(tracker.records)
                times.append(packet.timestamp_s)
                diagnostics.append(
                    {
                        "frame_id": packet.frame_id,
                        "timestamp_s": packet.timestamp_s,
                        "motion_status": result["motion_status"],
                        "flow_ml_min": result["flow_ml_min"],
                        "contrast": result["contrast"],
                        "displacement_px": result["displacement_px"],
                        "ignored_subminimum_count": len(
                            result["ignored_subminimum_features"]
                        ),
                        "ignored_subminimum_features": json.dumps(
                            result["ignored_subminimum_features"]
                        ),
                    }
                )
                if callback:
                    callback(packet, result)
                if render:
                    rel = packet.timestamp_s - first_s
                    # Fill the interval before this source timestamp with the preceding
                    # view.
                    while (
                        writer is not None
                        and last_dashboard is not None
                        and next_render < rel - 1e-9
                    ):
                        writer.write(last_dashboard)
                        next_render += 1 / 30
                    last_dashboard = draw_tracking(
                        packet.frame,
                        result,
                        cal,
                        summarize(tracker.records),
                        rolling=stats,
                    )
                    if packet.frame_id in (0, 100, 300, 600):
                        cv2.imwrite(
                            str(out / f"preview_frame_{packet.frame_id:04d}.jpg"),
                            last_dashboard,
                        )
            if tracker is None or cal is None or first_s is None:
                raise ValueError("Empty video.")
            if render and writer is not None and last_dashboard is not None:
                while next_render <= times[-1] - first_s + 1 / 30:
                    writer.write(last_dashboard)
                    next_render += 1 / 30
            timing_source = source.timing_source
        tracker.finish()
        gaps = np.diff(times)
        speeds = [d["flow_ml_min"] for d in diagnostics if d["flow_ml_min"] is not None]
        report = {
            "source_video": str(Path(video).resolve()),
            "timing_source": timing_source,
            "processed_frames": len(times),
            "source_duration_s": times[-1] - times[0],
            "achieved_source_fps": (len(times) - 1) / (times[-1] - times[0])
            if len(times) > 1
            else None,
            "maximum_frame_gap_s": float(max(gaps)) if len(gaps) else None,
            "processing_wall_s": time.monotonic() - start_wall,
            "calibration": cal,
            "summary": summarize(tracker.records),
            "mean_flow_ml_min": float(np.mean(speeds)) if speeds else None,
            "valid_speed_samples": len(speeds),
            "invalid_speed_samples": len(times) - len(speeds),
            "tracking_events": tracker.events,
            "validation_status": (
                "Offline replay only. No independent reference lengths or "
                "exhaustive manual count labels; zero missed/duplicate and "
                "length accuracy are not certified."
            ),
            "minimum_requested_slug_pixels": config["analysis"]["minimum_slug_mm"]
            / cal["mm_per_pixel"],
            "overlay_timing": (
                "30 fps presentation using preceding source frame; "
                "all source frames analysed at sidecar time"
            ),
        }
        export_results(out, tracker.records, diagnostics, report)
        return report
    finally:
        if writer is not None:
            writer.release()


def collect_live(config, duration_s=10, *, callback=None):
    """Collect a finite live window; include only tracks entering and exiting within
    it.
    """
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("Collection duration must be positive.")
    tracker = None
    flows = []
    timestamps = []
    invalid = 0
    with CameraSource(config) as source:
        negotiated = source.negotiated
        first = None
        for packet in source:
            if first is None or tracker is None:
                first = packet.timestamp_s
                cal = get_calibration(config, packet.frame)
                if not cal.get("reviewed", False):
                    raise ValueError(
                        "Live calibration must be reviewed before collection."
                    )
                tracker = SlugTracker(config, cal)
            if packet.timestamp_s - first > duration_s:
                break
            result = tracker.process(packet.frame, packet.timestamp_s, packet.frame_id)
            timestamps.append(packet.timestamp_s)
            if result["flow_ml_min"] is None:
                invalid += 1
            else:
                flows.append(result["flow_ml_min"])
            if callback:
                callback(packet, result)
    if tracker is None:
        raise ValueError("No frames received from the camera.")
    tracker.finish()
    return {
        "summary": summarize(tracker.records),
        "records": tracker.records,
        "mean_flow_ml_min": float(np.mean(flows)) if flows else None,
        "valid_speed_samples": len(flows),
        "invalid_speed_samples": invalid,
        "achieved_fps": (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
        if len(timestamps) > 1
        else None,
        "negotiated_camera_mode": negotiated,
        "tube_id_mm": config["geometry"]["tube_id_mm"],
    }


def live_view(config):
    """Display live tracking until Q, Escape, window close or interruption.

    Requires reviewed calibration at the negotiated camera resolution. Length
    cards and histograms use the trailing 10 seconds. Each accepted unique slug
    contributes once; speed/flow means use valid frame estimates only.
    """
    window = "Flow speed monitor v2 - live view"
    tracker = None
    cal = None
    window_open = False
    rolling = RollingMeasurements(10)
    last_render_s = -float("inf")
    try:
        with CameraSource(config) as source:
            for packet in source:
                if tracker is None or cal is None:
                    cal = get_calibration(config, packet.frame)
                    if not cal.get("reviewed", False):
                        raise ValueError(
                            "Live calibration must be reviewed. Run calibrate first."
                        )
                    tracker = SlugTracker(config, cal)
                    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                    window_open = True
                    cv2.resizeWindow(window, 1440, 900)
                result = tracker.process(
                    packet.frame, packet.timestamp_s, packet.frame_id
                )
                stats = rolling.update(result, tracker.records)
                if packet.timestamp_s - last_render_s >= 0.1:
                    dashboard = draw_tracking(
                        packet.frame, result, cal, live=True, rolling=stats
                    )
                    cv2.imshow(window, dashboard)
                    last_render_s = packet.timestamp_s
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
                # Keep indefinite viewing bounded: completed records are not exported.
                tracker.records.clear()
                tracker.events.clear()
                for track in tracker.active.values():
                    del track.lengths[:-300]
                    del track.sample_times[:-300]
    except KeyboardInterrupt:
        pass
    finally:
        if tracker is not None:
            tracker.finish()
        if window_open:
            cv2.destroyWindow(window)


def calibrate_live(config, config_path=DEFAULT_CONFIG_PATH, duration_s=4):
    """Sample passing live flow, require visual review, then persist the calibration."""
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("Calibration duration must be positive.")
    frames = []
    first = None
    with CameraSource(config) as source:
        for packet in source:
            if first is None:
                first = packet.timestamp_s
            if (
                len(frames) < 24
                and packet.timestamp_s - first >= len(frames) * duration_s / 24
            ):
                frames.append(_gray(packet.frame))
            if packet.timestamp_s - first >= duration_s:
                break
    cal = calibrate(frames, config)
    viewport, roi = review_calibration(cv2.cvtColor(frames[0], cv2.COLOR_GRAY2BGR), cal)
    cal = calibrate(
        frames, config, viewport=viewport, roi=roi, source="live reviewed setup"
    )
    cal["reviewed"] = True
    config["calibrations"]["{}x{}".format(*tuple(cal["resolution"]))] = cal
    save_config(config, config_path)
    return cal


def cli(config_path=DEFAULT_CONFIG_PATH):
    """Equipment-specific command mapping over the existing shared equipment CLI."""
    from Development.EQUIPMENT_CLI.equipment_cli import Command, run_cli

    def setup():
        return calibrate_live(load_config(config_path), config_path)

    def lengths():
        return collect_live(load_config(config_path), 10)["summary"]

    def flow():
        r = collect_live(load_config(config_path), 2)
        return {k: v for k, v in r.items() if k not in ("summary", "records")}

    run_cli(
        "Flow speed monitor v2",
        {
            "calibrate": Command(
                "calibrate — automatic ROI / threshold and manual review", setup
            ),
            "slugs": Command(
                "slugs — collect 10 s unique gas / solution mean lengths", lengths
            ),
            "flow": Command("flow — collect 2 s mean flow rate in mL/min", flow),
            "live": Command(
                "live — camera, phase detection, intensity and live measurements",
                lambda: live_view(load_config(config_path)),
            ),
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("cli")
    sub.add_parser("live", help="Open the live tracking interface")
    p = sub.add_parser("replay")
    p.add_argument("video", type=Path)
    p.add_argument("--timestamps", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--duration", type=float)
    p = sub.add_parser("calibrate-video")
    p.add_argument("video", type=Path)
    p.add_argument("--review", action="store_true")
    p.add_argument("--viewport", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--roi", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    args = parser.parse_args()
    if args.command == "cli":
        cli(args.config)
        return
    config = load_config(args.config)
    if args.command == "live":
        live_view(config)
        return
    if args.command == "calibrate-video":
        frames = sample_video(args.video)
        cal = calibrate(frames, config, viewport=args.viewport, roi=args.roi)
        if args.review:
            viewport, roi = review_calibration(frames[0], cal)
            cal = calibrate(
                frames,
                config,
                viewport=viewport,
                roi=roi,
                source="video manually reviewed",
            )
            cal["reviewed"] = True
        config["calibrations"]["{}x{}".format(*tuple(cal["resolution"]))] = cal
        save_config(config, args.config)
        print(json.dumps(cal, indent=2))
    else:
        report = replay_video(
            args.video,
            config,
            args.output,
            timestamps=args.timestamps,
            render=not args.no_render,
            duration_s=args.duration,
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "processed_frames",
                        "source_duration_s",
                        "summary",
                        "validation_status",
                    )
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
