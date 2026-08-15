#!/usr/bin/env pvpython
"""
Render a scalar field over the chamber volume, offscreen, with ParaView 5.11.2.

    pvpython scripts/render_field.py --case runs/<case>/ageEval \
        --field age --time 48.00000001 --out doc/ventilation

Built for the mean age of air -- the 3D ventilation map (CLAUDE.md 8.4) -- but it
takes any volScalarField.

Produces, in --out:
    01_volume.png       volume render -- where the stale air is, in 3D
    02_slice_x.png      mid-width cut (x = 60 mm): the hood, the jet, the tray
    03_slice_y.png      mid-depth cut (y = 93.3 mm)
    04_slice_z.png      port-centreline cut (z = 66.7 mm): the inlet -> outlet path
    05_tray_plane.png   the metric surface itself, z = 30 mm over the tray
    06_deadvolume.png   isosurface at the 75th percentile -- the worst-ventilated
                        volume, as a shape

COLOR
-----
`age` is a MAGNITUDE, so the map is SEQUENTIAL with monotonically increasing
lightness -- dark = fresh, bright = stale. Explicitly NOT a rainbow: rainbow maps
invent banding where the data is smooth and hide gradients where it is steep,
which on a field whose whole point is "where is the gradient" is disqualifying.
Inferno is used because it is perceptually uniform and stays legible printed and
in grayscale.

The scale is annotated in units of tau (V_air/Q) as well as seconds, because the
number that means something is the ratio: 1 tau is the exhaust age for ANY steady
flow, so anything well above 1 is dead volume.
"""

import argparse
import os

import paraview.servermanager
from paraview.simple import *  # noqa: F401,F403

BG = (0.10, 0.11, 0.13)
V_AIR = 2.530e-3          # m3, CLAUDE.md 6.1


def new_view(size=(1600, 1100)):
    v = CreateRenderView()
    v.ViewSize = list(size)
    v.Background = list(BG)
    v.UseColorPaletteForBackground = 0
    v.OrientationAxesVisibility = 1
    return v


def load(case, field, time):
    foam = os.path.join(case, "case.foam")
    open(foam, "a").close()
    src = OpenFOAMReader(registrationName="case.foam", FileName=foam)
    src.MeshRegions = ["internalMesh"]
    src.Decomposepolyhedra = 0
    # Read the timestep list BEFORE selecting arrays -- the array list is only
    # populated once the reader knows what times exist.
    src.UpdatePipelineInformation()
    times = list(src.TimestepValues) or [0.0]
    t = float(time) if time is not None else times[-1]
    src.CellArrays = [field]
    # ⚠ UpdatePipeline() with no time argument leaves the reader at t=0, where
    # the field does not exist yet -- GetArrayInformation then returns None and
    # the range lookup dies with an opaque AttributeError. Always pass the time.
    UpdatePipeline(time=t, proxy=src)
    # Cell data -> point data, so slices and isosurfaces interpolate smoothly
    # instead of showing the mesh.
    c2p = CellDatatoPointData(Input=src)
    UpdatePipeline(time=t, proxy=c2p)
    return src, c2p, t


def field_range(src, field, t):
    UpdatePipeline(time=t, proxy=src)
    di = src.GetDataInformation()
    ai = di.GetCellDataInformation().GetArrayInformation(field) or \
        di.GetPointDataInformation().GetArrayInformation(field)
    if ai is None:
        raise SystemExit(f"field '{field}' not found at t={t}")
    return ai.GetComponentRange(0)


def make_lut(field, lo, hi, tau):
    """Sequential, monotonic lightness, NOT a rainbow. See the module docstring.

    ⚠ AutomaticRescaleRangeMode MUST be "Never". ParaView's default rescales the
    lookup table to each *representation's* data range as it is shown, so every
    panel silently gets its own scale -- measured 2026-08-15, the x-slice came
    out -0.12..76 and the tray plane 21..68 from the same field. Six panels that
    look comparable and are not is worse than no panels: the same colour means a
    different age in each one.
    """
    lut = GetColorTransferFunction(field)
    lut.ApplyPreset("Inferno (matplotlib)", True)
    lut.AutomaticRescaleRangeMode = "Never"
    lut.RescaleTransferFunction(lo, hi)
    lut.NumberOfTableValues = 256
    pwf = GetOpacityTransferFunction(field)
    pwf.RescaleTransferFunction(lo, hi)
    return lut, pwf


def lock_scale(disp, view, lut, lo, hi):
    """Re-assert the shared range after Show(), and verify it stuck."""
    disp.LookupTable = lut
    disp.RescaleTransferFunctionToDataRange(False, True)
    lut.RescaleTransferFunction(lo, hi)
    got = lut.RGBPoints[0], lut.RGBPoints[-4]
    if abs(got[0] - lo) > 1e-6 * max(1.0, abs(hi)) or \
       abs(got[1] - hi) > 1e-6 * max(1.0, abs(hi)):
        print(f"  !! scale drifted to {got[0]:.4g}..{got[1]:.4g}, "
              f"expected {lo:.4g}..{hi:.4g}")


def add_bar(view, lut, field, tau):
    bar = GetScalarBar(lut, view)
    bar.Title = f"mean age of air  [s]     (tau = {tau:.2f} s)"
    bar.ComponentTitle = ""
    bar.TitleColor = [0.92, 0.92, 0.94]
    bar.LabelColor = [0.92, 0.92, 0.94]
    bar.TitleFontSize = 15
    bar.LabelFontSize = 13
    bar.ScalarBarLength = 0.5
    bar.WindowLocation = "Lower Right Corner"
    return bar


def save(view, path):
    Render(view)
    SaveScreenshot(path, view, ImageResolution=view.ViewSize,
                   TransparentBackground=0)
    print("  wrote", path)


def camera(view, pos, focal, up=(0, 0, 1), zoom=None):
    view.CameraPosition = list(pos)
    view.CameraFocalPoint = list(focal)
    view.CameraViewUp = list(up)
    if zoom:
        view.CameraParallelScale = zoom
    Render(view)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--field", default="age")
    ap.add_argument("--time", default=None)
    ap.add_argument("--out", default="doc/ventilation")
    ap.add_argument("--q", type=float, default=3.472222e-4,
                    help="volumetric flow [m3/s], for the tau annotation")
    a = ap.parse_args()

    tau = V_AIR / a.q
    os.makedirs(a.out, exist_ok=True)
    src, c2p, t = load(a.case, a.field, a.time)
    print(f"case {a.case}  field {a.field}  time {t}  tau {tau:.3f} s")

    raw_lo, hi = field_range(src, a.field, t)
    print(f"  raw range: {raw_lo:.4g} .. {hi:.4g}  "
          f"({raw_lo/tau:.2f} .. {hi/tau:.2f} tau)")
    # Clamp the colour floor at 0. `age` is a residence time and cannot be
    # negative; small negatives (~-1.6 s here, a fraction of a percent of the
    # range) are limitedLinear overshoot in a handful of cells. Mapping the
    # scale from the overshoot would spend contrast on a numerical artefact and
    # shift every colour, making the picture disagree with the reported volume
    # mean for no reason.
    lo = max(0.0, raw_lo)
    if raw_lo < 0:
        print(f"  clamping colour floor {raw_lo:.3g} -> 0 "
              f"(scheme overshoot, not physical)")
    print(f"  colour range: {lo:.4g} .. {hi:.4g}  "
          f"({lo/tau:.2f} .. {hi/tau:.2f} tau)")
    lut, pwf = make_lut(a.field, lo, hi, tau)

    # Volume-weighted mean, for the dead-volume threshold. IntegrateVariables
    # divides by total volume when DivideCellDataByVolume is on.
    iv = IntegrateVariables(Input=src)
    iv.DivideCellDataByVolume = 1
    UpdatePipeline(time=t, proxy=iv)
    vol_mean = paraview.servermanager.Fetch(iv).GetCellData() \
        .GetArray(a.field).GetValue(0)
    print(f"  volume mean: {vol_mean:.4g} s = {vol_mean/tau:.2f} tau")

    # centre of the chamber, for camera aiming (CLAUDE.md 6.1 geometry)
    ctr = (0.0633, 0.0933, 0.055)

    # --- 1. volume render -------------------------------------------------
    v = new_view()
    v.ViewTime = t
    d = Show(c2p, v)
    d.SetRepresentationType("Volume")
    ColorBy(d, ("POINTS", a.field))
    lock_scale(d, v, lut, lo, hi)
    d.ScalarOpacityFunction = pwf
    d.ScalarOpacityUnitDistance = 0.004
    add_bar(v, lut, a.field, tau)
    d.SetScalarBarVisibility(v, True)
    camera(v, (0.32, -0.22, 0.20), ctr)
    save(v, os.path.join(a.out, "01_volume.png"))
    Delete(v)

    # --- 2-4. orthogonal slices -------------------------------------------
    for name, origin, normal, cam in [
        ("02_slice_x", (0.0633, 0.0933, 0.055), (1, 0, 0), (0.45, 0.0933, 0.055)),
        ("03_slice_y", (0.0633, 0.0933, 0.055), (0, 1, 0), (0.0633, -0.30, 0.055)),
        ("04_slice_z", (0.0633, 0.0933, 0.0667), (0, 0, 1), (0.0633, 0.0933, 0.36)),
    ]:
        v = new_view()
        v.ViewTime = t
        sl = Slice(Input=c2p)
        sl.SliceType = "Plane"
        sl.SliceType.Origin = list(origin)
        sl.SliceType.Normal = list(normal)
        d = Show(sl, v)
        d.Representation = "Surface"
        ColorBy(d, ("POINTS", a.field))
        lock_scale(d, v, lut, lo, hi)
        add_bar(v, lut, a.field, tau)
        d.SetScalarBarVisibility(v, True)
        up = (0, 0, 1) if normal[2] == 0 else (0, 1, 0)
        camera(v, cam, origin, up)
        v.ResetCamera()
        save(v, os.path.join(a.out, name + ".png"))
        Delete(v)

    # --- 5. the tray plane -- the metric surface (CLAUDE.md 10.4 Q8) -------
    v = new_view()
    v.ViewTime = t
    sl = Slice(Input=c2p)
    sl.SliceType = "Plane"
    sl.SliceType.Origin = [0.06, 0.0933, 0.030]
    sl.SliceType.Normal = [0, 0, 1]
    d = Show(sl, v)
    d.Representation = "Surface"
    ColorBy(d, ("POINTS", a.field))
    lock_scale(d, v, lut, lo, hi)
    add_bar(v, lut, a.field, tau)
    d.SetScalarBarVisibility(v, True)
    camera(v, (0.06, 0.0933, 0.30), (0.06, 0.0933, 0.030), (0, 1, 0))
    v.ResetCamera()
    save(v, os.path.join(a.out, "05_tray_plane.png"))
    Delete(v)

    # --- 6. the dead volume, as a shape -----------------------------------
    # A Contour gives the SHELL of the region -- a sheet floating in space with
    # nothing to locate it against. Rendered that way (first attempt,
    # 2026-08-15) it was unreadable. What the question "where is the dead air"
    # actually wants is the enclosed VOLUME, plus the chamber outline for
    # reference. So: Threshold, not Contour, over a translucent boundary.
    #
    # Threshold at 1.5x the volume mean rather than a percentile of the RANGE:
    # the range top is one extreme cell, whereas "half again worse than the
    # chamber average" is a statement about the flow.
    thr = 1.5 * vol_mean
    v = new_view()
    v.ViewTime = t

    outline = ExtractBlock(Input=src)
    outline.Selectors = ["/Root/boundary"]
    od = Show(outline, v)
    od.Representation = "Surface"
    od.ColorArrayName = [None, ""]
    od.DiffuseColor = [0.55, 0.58, 0.62]
    od.Opacity = 0.10

    th = Threshold(Input=c2p)
    th.Scalars = ["POINTS", a.field]
    th.LowerThreshold = thr
    th.UpperThreshold = hi
    th.ThresholdMethod = "Between"
    d = Show(th, v)
    d.Representation = "Surface"
    ColorBy(d, ("POINTS", a.field))
    lock_scale(d, v, lut, lo, hi)
    d.Opacity = 0.92
    add_bar(v, lut, a.field, tau)
    d.SetScalarBarVisibility(v, True)
    camera(v, (0.34, -0.24, 0.22), ctr)
    v.ResetCamera()
    save(v, os.path.join(a.out, "06_deadvolume.png"))
    print(f"  dead volume = cells with age > {thr:.3g} s "
          f"= {thr/tau:.2f} tau = 1.5x the volume mean")
    Delete(v)


if __name__ == "__main__":
    main()
