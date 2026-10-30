from pathlib import Path

import numpy as np
import pyFAI

import KRAIC_I11_1.fep_subtraction.fep2d_pipeline as fp
import KRAIC_I11_1.fep_subtraction.fep2d_v3 as fm
from KRAIC_I11_1.fep_subtraction.fep2d_inline import (
    InlineSubtractor,
    append_log,
    watch_folder,
)
from KRAIC_I11_1.fep_subtraction.fep2d_pipeline import Settings
from KRAIC_I11_1.logger import LOGGER


def run_subtraction_on_frame(
    frame_2d: np.ndarray,
    merged_reference_npz_path: str,
    poni_path: str,
    mask_npy_path: str,
    settings: Settings,
):

    sub = InlineSubtractor(
        fm.load_reference(merged_reference_npz_path),
        pyFAI.load(poni_path),
        np.load(mask_npy_path),
        settings=settings,
    )
    result = sub.process(frame_2d, name="pixium_146588")  # never raises
    LOGGER.info(
        result.name,
        "OK" if result.ok else "FAILED",
        f"{result.seconds:.2f}s",
        *result.flags,
    )

    return result


def run_watcher_with_settings(
    watch_path: str,
    outpath: str,
    run_name: str,
    merged_reference_npz_path: str,
    poni_path: str,
    mask_npy_path: str | None,
    settings: Settings,
    ext: str = ".hdf",
    log_name: str = "inline_log.csv",
):

    if "processed" not in outpath:
        raise ValueError("You should only be writing data to /processed folders!")

    sub = InlineSubtractor(
        fm.load_reference(merged_reference_npz_path),
        pyFAI.load(poni_path),
        np.load(mask_npy_path) if mask_npy_path else None,
        settings=settings,
    )
    for w in sub.warnings:
        LOGGER.warning(w)
    run_dir = Path(outpath) / run_name
    out = run_dir / "01_corrected_2D"
    fp.write_manifest(
        run_dir / "inline_manifest.json",
        reference=merged_reference_npz_path,
        reference_label=sub.ref.label,
        reference_n_frames=sub.ref.n_used,
        poni=poni_path,
        mask=mask_npy_path,
        watch=watch_path,
        settings=settings.as_dict(),
        reference_warnings=sub.warnings,
    )
    LOGGER.info(f"watching {watch_path}  ->  {out}   (Cancel to stop)")
    try:
        for p in watch_folder(watch_path, (ext,)):
            for result in sub.process_file(p, out):
                append_log(result, run_dir / log_name)
                LOGGER.info(
                    " ".join(
                        [
                            result.name,
                            "OK" if result.ok else "FAILED",
                            f"{result.seconds:.2f}s",
                            *result.flags,
                        ]
                    )
                )
    except KeyboardInterrupt:
        LOGGER.info("stopped")


def run_watcher(
    watch_path: str,
    outpath: str,
    run_name: str,
    merged_reference_npz_path: str,
    poni_path: str,
    mask_npy_path: str | None,
    extra_mask: list[tuple[float, float]] | None = None,
    npt: int = 2000,
    rmin: float = 1.0,
    rmax: float = 30.0,
    half_window: int = 4,
    zero_masked: bool = True,
    fit_stride: int = 1,
    scale_bounds: tuple[float, float] = (0.3, 3.0),
    min_total_frac: float = 0.30,
    min_fit_frac: float = 0.50,
    drift_sigma: float = 5.0,
    noise_factor: float = 2.0,
    min_history: int = 10,
    ext: str = ".hdf",
    log_name: str = "inline_log.csv",
):
    """Build the Settings from the arguments and run the watcher.
    extra_mask=None uses fp.DEFAULT_EXTRA_MASK; pass [] for no extra mask."""

    if extra_mask is None:
        extra_mask = list(fp.DEFAULT_EXTRA_MASK)

    settings = Settings(
        extra_mask=extra_mask,
        npt=npt,
        rmin=rmin,
        rmax=rmax,
        half_window=half_window,
        zero_masked=zero_masked,
        fit_stride=fit_stride,
        scale_bounds=scale_bounds,
        min_total_frac=min_total_frac,
        min_fit_frac=min_fit_frac,
        drift_sigma=drift_sigma,
        noise_factor=noise_factor,
        min_history=min_history,
    )
    run_watcher_with_settings(
        watch_path=watch_path,
        outpath=outpath,
        run_name=run_name,
        merged_reference_npz_path=merged_reference_npz_path,
        poni_path=poni_path,
        mask_npy_path=mask_npy_path,
        settings=settings,
        ext=ext,
        log_name=log_name,
    )
