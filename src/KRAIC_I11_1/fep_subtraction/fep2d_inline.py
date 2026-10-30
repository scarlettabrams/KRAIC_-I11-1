"""
fep2d_inline.py  -  inline 2D FEP subtraction: raw 2D frame in, corrected 2D frame out
========================================================================================
One job only. The merged reference (.npz) is built beforehand in the offline app from
frames collected before the crystal solution runs. During the experiment this script
subtracts it, frame by frame, from each raw frame and writes the corrected frame as a
2D file. Diffraction sorting, integration and baselining then happen in the offline app
(tabs 3 to 5), on this script's output.

The maths is the offline app's tab 2, unchanged (fep2d_v3.subtract_frame): one robust
scale factor per frame fitted on the whole detector, no offset,
frame - scale * reference, negative values kept, masked pixels set to 0. The output
files, names and subtraction_diagnostics.csv are the same as tab 2 writes, so the app
reads them without any change.

Use from code
-------------
    import numpy as np, pyFAI, fep2d_v3 as fm
    from fep2d_inline import InlineSubtractor

    # once, about 1 s
    sub = InlineSubtractor(fm.load_reference("merged_reference.npz"),
                           pyFAI.load("calib.poni"), np.load("mask.npy"))
    res = sub.process(frame_2d, name="pixium_146588")  # numpy array in, never raises
    res.ok, res.flags        # False or flags = look at this frame
    res.corrected            # float32 2D array, same shape as the frame
    res.scale                # fitted scale factor

    # reads, subtracts, writes
    sub.process_file("pixium_146588.hdf", "E:/out/Run7/01_corrected_2D")

Folder watching
---------------
    python fep2d_inline.py --ref merged_reference.npz --poni calib.poni \\
        --mask mask.npy --watch E:/run/frames --out E:/out --run Run7

writes  <out>/<run>/01_corrected_2D/<same file name as the raw frame>
        <out>/<run>/01_corrected_2D/subtraction_diagnostics.csv
            (same columns as the app's tab 2)
        <out>/<run>/inline_log.csv          (one line per frame, with flags)
        <out>/<run>/inline_manifest.json    (settings, reference, files used)

A frame that fails a hard check is NOT written and is logged with the reason, so a
closed-shutter or corrupt frame never reaches the sorting step. One bad file never
stops the run.
"""

from __future__ import annotations

import collections
import csv
import os
import stat
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

import KRAIC_I11_1.fep_subtraction.fep2d_pipeline as fp
import KRAIC_I11_1.fep_subtraction.fep2d_v3 as fm
from KRAIC_I11_1.fep_subtraction.fep2d_pipeline import InputError, Settings

if TYPE_CHECKING:
    from pyFAI.integrator.azimuthal import AzimuthalIntegrator

DIAG_FIELDS = [
    "order",
    "file",
    "frame",
    "scale",
    "offset",
    "fit_pixel_frac",
    "neg_frac",
    "corrected_sum",
]


class SubResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    ok: bool
    flags: list = Field(default_factory=list)
    corrected: np.ndarray | None = None
    info: dict = Field(default_factory=dict)
    scale: float = float("nan")
    fit_frac: float = float("nan")
    seconds: float = 0.0
    written: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "flags": ";".join(self.flags),
            "scale": round(self.scale, 4),
            "fit_frac": round(self.fit_frac, 3),
            "seconds": round(self.seconds, 3),
            "written": self.written,
        }


class InlineSubtractor:
    def __init__(
        self,
        ref: fm.Reference,
        ai: AzimuthalIntegrator | None = None,
        det_mask: np.ndarray | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.s = settings or Settings()
        self.ref = ref
        self.shape = tuple(ref.mean.shape)
        self.warnings = fp.check_reference(ref)  # raises InputError if unusable
        if self.s.extra_mask and ai is None:
            raise InputError("the extra 2-theta mask needs the calibration (.poni)")
        self.mask = fp.total_mask(det_mask, ai, self.shape, self.s.extra_mask)
        if int((~self.mask).sum()) < 1000:
            raise InputError("fewer than 1000 usable pixels after masking")
        self._ref_total = float(ref.mean[~self.mask].sum())
        self._scales: collections.deque[float] = collections.deque(maxlen=200)
        self._order = 0

    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, name: str = "frame") -> SubResult:
        t0 = time.time()
        r = SubResult(name=name, ok=False)
        try:
            frame = np.asarray(frame)
            if frame.shape != self.shape:
                raise InputError(
                    f"frame is {frame.shape} but the reference is {self.shape}"
                )
            frame = frame.astype(np.float32)
            if not np.isfinite(frame).all():
                r.flags.append("non_finite_pixels")
                raise InputError("frame contains NaN or infinite pixels")
            if float(frame[~self.mask].sum()) < self.s.min_total_frac * self._ref_total:
                r.flags.append("low_total")
                raise InputError(
                    "frame total is far below the reference (shutter closed or dark?)"
                )
            corr, info = fm.subtract_frame(frame, self.ref, self.mask)
            r.corrected, r.info = corr, info
            r.scale, r.fit_frac = info["scale"], info["fit_pixel_frac"]
            r.ok = True
            self._soft_flags(r)
        except InputError as e:
            r.flags.append(f"rejected: {e}")
        except Exception as e:  # never stop an experiment
            r.flags.append(f"error: {type(e).__name__}: {e}")
        r.seconds = time.time() - t0
        return r

    def _soft_flags(self, r: SubResult) -> None:
        s = self.s
        lo, hi = s.scale_bounds
        if not (lo <= r.scale <= hi):
            r.flags.append(f"scale_out_of_range ({r.scale:.2f})")
        if r.fit_frac < s.min_fit_frac:
            r.flags.append(f"fit_unstable (kept {r.fit_frac:.2f} of pixels)")
        if len(self._scales) >= s.min_history:
            med = float(np.median(self._scales))
            mad = 1.4826 * float(np.median(np.abs(np.array(self._scales) - med))) + 1e-9
            if abs(r.scale - med) > s.drift_sigma * mad:
                r.flags.append(f"scale_drift (median {med:.3f})")
        self._scales.append(r.scale)

    # ------------------------------------------------------------------
    def process_file(
        self, path: fm.PathLike, out_dir: fm.PathLike, suffix: str = ""
    ) -> list[SubResult]:
        """Read a raw .hdf/.nxs (2D or 3D), subtract, and write each corrected frame to
        out_dir under the same name as tab 2 of the app does. Returns one SubResult per
        frame."""
        path, out_dir = Path(path), Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []
        try:
            nfr = fm.n_frames_in_file(path)
            for _, i, fr in fm.iter_frames([path]):
                stem = path.stem + (f"_f{i:04d}" if nfr > 1 else "")
                r = self.process(fr, stem + path.suffix)
                if r.ok and r.corrected is not None:
                    try:
                        dst = out_dir / f"{stem}{suffix}{path.suffix}"
                        tmp = (
                            out_dir / f".part_{dst.name}"
                        )  # written under a hidden name, then renamed,
                        fm.write_corrected_nxs(
                            path, tmp, r.corrected, i, self.ref, r.info
                        )  # so a reader never
                        os.chmod(
                            tmp, stat.S_IREAD | stat.S_IWRITE
                        )  # raw files are often read-only and the copy
                        os.replace(tmp, dst)  # inherits that; sees a half-written file
                        r.written = str(dst)
                        self._append_diag(out_dir, path.name, i, r.info)
                    except Exception as e:
                        r.ok = False
                        r.flags.append(f"write_failed: {type(e).__name__}: {e}")
                results.append(r)
        except Exception as e:
            results.append(
                SubResult(
                    name=path.name,
                    ok=False,
                    flags=[f"unreadable: {type(e).__name__}: {e}"],
                )
            )
        return results

    def _append_diag(
        self, out_dir: Path, fname: str, frame_idx: int, info: dict[str, float]
    ) -> None:
        p = out_dir / "subtraction_diagnostics.csv"
        new = not p.exists()
        with open(p, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=DIAG_FIELDS)
            if new:
                w.writeheader()
            w.writerow(dict(order=self._order, file=fname, frame=frame_idx, **info))
        self._order += 1


# ----------------------------------------------------------------------------
# logging and watching
# ----------------------------------------------------------------------------
def append_log(res: SubResult, log_path: fm.PathLike) -> None:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new = not log_path.exists()
    with open(log_path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res.summary().keys()))
        if new:
            w.writeheader()
        w.writerow(res.summary())


def _readable(p: fm.PathLike) -> bool:
    """True once the file opens as HDF5 (a file still being written usually does
    not)."""
    try:
        import h5py

        with h5py.File(p, "r"):
            return True
    except Exception:
        return False


def watch_folder(
    folder: fm.PathLike,
    exts: Sequence[str] = (".hdf",),
    poll: float = 1.0,
    settle: float = 0.5,
    stop: Callable[[], bool] = lambda: False,
    give_up_s: float = 60.0,
) -> Iterator[Path]:
    """Yield each NEW frame file once. A file is passed on when its size has stopped
    changing AND it opens as HDF5. If it still cannot be opened after give_up_s seconds
    it is passed on anyway, so it is logged as a failed frame instead of being silently
    skipped.
    Default is .hdf only: each .nxs links to its .hdf, so watching both counts every
    frame twice."""
    seen, first_seen, folder = set(), {}, Path(folder)
    exts = tuple(e.lower() for e in exts)
    while not stop():
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() in exts and p not in seen:
                first_seen.setdefault(p, time.time())
                s1 = p.stat().st_size
                time.sleep(settle)
                if p.stat().st_size != s1 or s1 == 0:
                    continue
                if _readable(p) or time.time() - first_seen[p] > give_up_s:
                    seen.add(p)
                    yield p
        time.sleep(poll)
