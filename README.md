# FEP 2D frame subtraction (I11 PXRD)

Removes the scattering of the FEP flow tube from each raw 2D detector frame (Pixium, 2881 x 2880), so that the crystal diffraction can be analysed.

One frame in, one corrected frame out:

1. A merged reference (`merged_reference.npz`, mean of 46 or more tube-only frames) is built beforehand in the offline app.
2. For each new frame, one robust scale factor `s` is fitted (Bragg spots rejected).
3. `corrected = frame - s * reference`; masked pixels (detector mask and a 2theta ring 5.30 to 6.10 deg) are set to 0; negatives are kept.

## Files

| File | Purpose |
|---|---|
| `fep2d_inline.py` | `InlineSubtractor` class, folder watcher, command line |
| `fep2d_pipeline.py` | Shared settings, mask building, reference checks |
| `fep2d_v3.py` | Core maths and HDF5 reading and writing |
| `docs/README_inline.md` | Engineering notes: interface, checks, outputs, speed, limits |
| `docs/Engineering_Handover_2D_FEP_Subtraction.pptx` | Meeting slides |

## Install

```
pip install -r requirements.txt
```

## Use

```python
import numpy as np, pyFAI
import fep2d_v3 as fm
from fep2d_inline import InlineSubtractor

sub = InlineSubtractor(
    fm.load_reference("merged_reference.npz"),
    pyFAI.load("calib.poni"),
    np.load("mask.npy"),
)
res = sub.process(frame_2d, name="pixium_146588")  # never raises
res.ok, res.flags, res.scale, res.corrected
```

Folder watcher:

```
python fep2d_inline.py --ref merged_reference.npz --poni calib.poni --mask mask.npy \
    --watch E:/run/frames --out E:/out --run Run7
```

## Status

Tested on recorded I11 frames (AP39, carbamazepine); output matches the offline app pixel for pixel on 4 real frames. About 4.2 s per frame including writing, on 2 CPU cores. Not yet run on a live beamline feed. Peak memory and concurrent use are not yet measured or tested.


## Installation

To install this project (on linux or Mac) run:

```bash
git clone https://github.com/scarlettabrams/KRAIC_I11_1.git

cd KRAIC_I11_1

pip install .[dev]

```

## Code quality + VSCode

There have been a load of tools (that work in VSCode) to hopefully improve code quality, and therefore prevent any issues during runtime.

You must have docker installed on your machine.

In order to enter this development environment, open this code in VSCode and a little pop-up should show up asking you to re-open in dev container

Alternatively you can either press Command + Shift + P and rebuild or re-open in dev container

When you open a terminal in VSCode there will now be a tab at the bottom "Problems", if there are any issues with your code, this Problems tab will show you what needs fixing

Having robots nit-pick your code is annoying, but believe me it makes sure things run properly and prevent issues during runtime.

Ideally we would write unit tests too - but this is experimental code, so we'll live without


### Running this at end of Scan:

```bash
curl -X POST https://i11-analysise.diamond.ac.uk/analyse -H "Content-Type: application/json" -d '{
  "analysis_name": "run_subtraction_on_file",
  "inputs": {
    "file_path": "<path/to/raw.nxs>",
    "outpath": "<path/to/processed/output_dir>",
    "run_name": "<run_name>",
    "merged_reference_npz_path": "<path/to/merged_reference.npz>",
    "poni_path": "<path/to/calibration.poni>",
    "mask_npy_path": "<path/to/mask.npy>",
    "extra_mask": null,
    "npt": 2000,
    "rmin": 1.0,
    "rmax": 30.0,
    "half_window": 4,
    "zero_masked": true,
    "fit_stride": 1,
    "scale_bounds": [0.3, 3.0],
    "min_total_frac": 0.30,
    "min_fit_frac": 0.50,
    "drift_sigma": 5.0,
    "noise_factor": 2.0,
    "min_history": 10,
    "log_name": "inline_log.csv"
  }
}'
```bash
