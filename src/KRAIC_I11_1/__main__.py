import argparse
from collections.abc import Sequence
from pathlib import Path

import numpy as np

import KRAIC_I11_1.fep_subtraction.fep2d_pipeline as fp
import KRAIC_I11_1.fep_subtraction.fep2d_v3 as fm
from KRAIC_I11_1.fep_subtraction.fep2d_inline import (
    InlineSubtractor,
    Settings,
    append_log,
    watch_folder,
)


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Inline 2D FEP subtraction (folder watcher)"
    )
    ap.add_argument(
        "--ref", required=True, help="merged reference .npz made in the offline app"
    )
    ap.add_argument("--poni", required=True)
    ap.add_argument(
        "--mask", default=None, help="detector mask .npy (True = bad pixel)"
    )
    ap.add_argument("--watch", required=True, help="folder to watch for new raw frames")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--run", default="run")
    ap.add_argument(
        "--extra-mask",
        default=fp.fmt_ranges(fp.DEFAULT_EXTRA_MASK),
        help="extra 2-theta mask, e.g. 5.30-6.10 (use '' for none)",
    )
    ap.add_argument("--ext", default=".hdf")
    a = ap.parse_args(argv)
    import pyFAI

    s = Settings(extra_mask=fp.parse_ranges(a.extra_mask))
    sub = InlineSubtractor(
        fm.load_reference(a.ref),
        pyFAI.load(a.poni),
        np.load(a.mask) if a.mask else None,
        s,
    )
    for w in sub.warnings:
        print("WARNING:", w)
    run_dir = Path(a.out) / a.run
    out = run_dir / "01_corrected_2D"
    fp.write_manifest(
        run_dir / "inline_manifest.json",
        reference=a.ref,
        reference_label=sub.ref.label,
        reference_n_frames=sub.ref.n_used,
        poni=a.poni,
        mask=a.mask,
        watch=a.watch,
        settings=s.as_dict(),
        reference_warnings=sub.warnings,
    )
    print(f"watching {a.watch}  ->  {out}   (Ctrl+C to stop)")
    try:
        for p in watch_folder(a.watch, (a.ext,)):
            for res in sub.process_file(p, out):
                append_log(res, run_dir / "inline_log.csv")
                print(
                    res.name,
                    "OK" if res.ok else "FAILED",
                    f"{res.seconds:.2f}s",
                    *res.flags,
                )
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
