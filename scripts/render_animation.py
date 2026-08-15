#!/usr/bin/env pvpython
"""
Render a time sequence of a field on a slice, offscreen, for animation.

    pvpython scripts/render_animation.py --case runs/<case> --field 'mag(U)' \
        --slice x --out doc/animation

Then assemble (no ffmpeg on this box -- Pillow writes the GIF):

    python3 scripts/make_gif.py doc/animation

WHAT TO ANIMATE
---------------
The FLOW: `mag(U)`, `U`, or in Phase 2 `T`. These are instantaneous fields and a
frame of one means something.

NOT `age`. It solves a *steady* transport equation, so a per-frame age answers
"what age field would this instant's flow have if it persisted forever" -- which
is not the mean age of air and not a quantity anyone wants (CLAUDE.md 8.4). The
ventilation map is ONE age field computed on the time-averaged flux `phiMean`;
see scripts/render_field.py. This script refuses `--field age` for that reason.

FIXED COLOUR SCALE
------------------
Every frame shares one scale, computed once over the whole sequence. ParaView's
default rescales per frame, which makes the colours pulse with the range instead
of with the flow -- the animation then shows the normalisation moving, not the
physics, and a viewer cannot tell the two apart. Same trap as the six static
panels (see render_field.py); it is worse here because it looks like motion.
"""

import argparse
import glob
import os

import paraview.servermanager
from paraview.simple import *  # noqa: F401,F403

BG = (0.10, 0.11, 0.13)

SLICES = {
    # name: (origin, normal, camera position, view-up)
    "x": ((0.0633, 0.0933, 0.055), (1, 0, 0), (0.45, 0.0933, 0.055), (0, 0, 1)),
    "y": ((0.0633, 0.0933, 0.055), (0, 1, 0), (0.0633, -0.30, 0.055), (0, 0, 1)),
    "z": ((0.0633, 0.0933, 0.0667), (0, 0, 1), (0.0633, 0.0933, 0.36), (0, 1, 0)),
}


def case_times(case):
    """Reconstructed time directories, numerically sorted."""
    out = []
    for d in glob.glob(os.path.join(case, "[0-9]*")):
        b = os.path.basename(d)
        if not os.path.isdir(d):
            continue
        try:
            out.append((float(b), b))
        except ValueError:
            pass          # 0.orig and friends
    return [b for _, b in sorted(out)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--field", default="mag(U)")
    ap.add_argument("--slice", default="x", choices=list(SLICES))
    ap.add_argument("--out", default="doc/animation")
    ap.add_argument("--from-time", type=float, default=None)
    ap.add_argument("--size", default="1280x900")
    a = ap.parse_args()

    if a.field == "age":
        raise SystemExit(
            "refusing --field age: it is a STEADY quantity and a per-frame age is\n"
            "meaningless on an unsteady flow (CLAUDE.md 8.4). Animate mag(U)/U/T;\n"
            "for the ventilation map use scripts/render_field.py on phiMean.")

    w, h = (int(v) for v in a.size.split("x"))
    os.makedirs(a.out, exist_ok=True)

    foam = os.path.join(a.case, "case.foam")
    open(foam, "a").close()
    src = OpenFOAMReader(registrationName="case.foam", FileName=foam)
    src.MeshRegions = ["internalMesh"]
    src.Decomposepolyhedra = 0
    src.UpdatePipelineInformation()
    times = [t for t in (src.TimestepValues or [])
             if a.from_time is None or t >= a.from_time]
    if not times:
        raise SystemExit(f"no reconstructed times in {a.case} "
                         f"(reconstructPar first)")
    src.CellArrays = [a.field]
    print(f"{len(times)} frames: {times[0]} .. {times[-1]}")

    c2p = CellDatatoPointData(Input=src)

    # --- one scale for the whole sequence --------------------------------
    lo, hi = None, None
    for t in times:
        UpdatePipeline(time=t, proxy=src)
        ai = src.GetDataInformation().GetCellDataInformation() \
            .GetArrayInformation(a.field)
        if ai is None:
            continue
        r = ai.GetComponentRange(0)
        lo = r[0] if lo is None else min(lo, r[0])
        hi = r[1] if hi is None else max(hi, r[1])
    lo = max(0.0, lo)
    print(f"  shared colour scale: {lo:.4g} .. {hi:.4g}")

    lut = GetColorTransferFunction(a.field)
    lut.ApplyPreset("Viridis (matplotlib)", True)
    lut.AutomaticRescaleRangeMode = "Never"
    lut.RescaleTransferFunction(lo, hi)

    origin, normal, campos, up = SLICES[a.slice]
    view = CreateRenderView()
    view.ViewSize = [w, h]
    view.Background = list(BG)
    view.UseColorPaletteForBackground = 0
    view.OrientationAxesVisibility = 0

    sl = Slice(Input=c2p)
    sl.SliceType = "Plane"
    sl.SliceType.Origin = list(origin)
    sl.SliceType.Normal = list(normal)
    d = Show(sl, view)
    d.Representation = "Surface"
    ColorBy(d, ("POINTS", a.field))
    d.LookupTable = lut
    d.RescaleTransferFunctionToDataRange(False, True)
    lut.RescaleTransferFunction(lo, hi)

    bar = GetScalarBar(lut, view)
    bar.Title = a.field
    bar.ComponentTitle = "[m/s]" if "U" in a.field else ""
    bar.TitleColor = [0.92, 0.92, 0.94]
    bar.LabelColor = [0.92, 0.92, 0.94]
    bar.ScalarBarLength = 0.45
    bar.WindowLocation = "Lower Right Corner"
    d.SetScalarBarVisibility(view, True)

    txt = Text(Text="")
    td = Show(txt, view)
    td.Color = [0.92, 0.92, 0.94]
    td.FontSize = 16
    td.WindowLocation = "Upper Left Corner"

    view.CameraPosition = list(campos)
    view.CameraFocalPoint = list(origin)
    view.CameraViewUp = list(up)
    Render(view)
    view.ResetCamera()

    for i, t in enumerate(times):
        view.ViewTime = t
        UpdatePipeline(time=t, proxy=c2p)
        txt.Text = f"t = {t:7.2f} s"
        # re-assert: some filters quietly rescale on update
        lut.RescaleTransferFunction(lo, hi)
        Render(view)
        p = os.path.join(a.out, f"frame_{i:04d}.png")
        SaveScreenshot(p, view, ImageResolution=[w, h],
                       TransparentBackground=0)
        if i % 10 == 0 or i == len(times) - 1:
            print(f"  frame {i:4d}/{len(times) - 1}  t={t:.2f}")
    print(f"wrote {len(times)} frames to {a.out}")


if __name__ == "__main__":
    main()
