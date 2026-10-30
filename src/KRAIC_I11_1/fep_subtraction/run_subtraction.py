import numpy as np
import pyFAI

import KRAIC_I11_1.fep2d_v3 as fm
from KRAIC_I11_1.fep2d_inline import InlineSubtractor


def run_subtraction(
    frame_2d: np.ndarray,
    merged_reference_npz_path: str,
    calibration_poni_path: str,
    mask_npy_path: str,
):

    sub = InlineSubtractor(
        fm.load_reference(merged_reference_npz_path),
        pyFAI.load(calibration_poni_path),
        np.load(mask_npy_path),
    )
    result = sub.process(frame_2d, name="pixium_146588")  # never raises
    return result
