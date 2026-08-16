#!/usr/bin/env pvpython
"""
Render mesh inspection images for a case, offscreen, with ParaView 5.11.2.

Run with pvpython (NOT python3 -- the paraview module is not on the system
python path):

    pvpython scripts/render_mesh.py --case runs/p1_baseline_m2 [--out doc/mesh]

Produces, in --out:
    01_patches.png      exterior, coloured by patch -- checks the hood, ports
                        and tray came out where CLAUDE.md 6.1 says they should
    02_slice_x.png      mid-width cut (x = 60 mm): hood profile, tray, the
                        vertical stack-up
    03_slice_y.png      mid-depth cut (y = 93.3 mm): tray, walls, hood
    04_slice_z.png      port-centreline cut (z = 66.7 mm): the jet path
    05_tray_wall_junction.png
                        close-up of the tray-top/side-wall corner -- where the
                        two 4-layer stacks meet, and the first place layer
                        collapse shows up
    06_cutaway.png      quarter cutaway, for the overall sense of the volume

ALWAYS check total volume against V_air = 2.3296e-3 m3 in log.checkMesh, not
just "Mesh OK". The tray no longer has side slots for snappy to seal, but the
lesson that produced this warning still stands: a sealed feature is invisible to
every mesh metric except the volume. At m0 with level-2 tray refinement snappy
used to close both 2.5 mm slots, and the only symptom was 15.5 mL missing.
"""

import argparse
import os

from paraview.simple import *  # noqa: F401,F403

# Patch colours. Deliberately flat and distinct -- this is an inspection
# render, not a presentation figure.
PATCH_RGB = {
    "inlet":  (0.16, 0.55, 0.85),
    "outlet": (0.90, 0.40, 0.25),
    "hood":   (0.75, 0.75, 0.78),
    "walls":  (0.62, 0.66, 0.70),
    "floor":  (0.45, 0.48, 0.52),
    "tray":   (0.35, 0.62, 0.35),
}

BG = (0.10, 0.11, 0.13)
EDGE = (0.05, 0.05, 0.06)


def new_view(size=(1600, 1100)):
    v = CreateRenderView()
    v.ViewSize = list(size)
    v.Background = list(BG)
    v.UseColorPaletteForBackground = 0
    v.OrientationAxesVisibility = 1
    return v


def load(case):
    foam = os.path.join(case, "case.foam")
    open(foam, "a").close()
    src = OpenFOAMReader(registrationName="case.foam", FileName=foam)
    src.MeshRegions = ["internalMesh"] + \
        ["patch/" + p for p in PATCH_RGB]
    src.CellArrays = []
    src.Decomposepolyhedra = 0
    src.UpdatePipeline()
    return src


def extract_patch(src, name):
    b = ExtractBlock(Input=src)
    # ParaView 5.11 selects by assembly path. The OpenFOAM reader nests patches
    # under /Root/boundary/<patch> -- "/Root/<patch>" silently matches nothing
    # and you get an empty render rather than an error.
    b.Selectors = ["/Root/boundary/" + name]
    return b


def save(view, path):
    Render(view)
    SaveScreenshot(path, view, ImageResolution=view.ViewSize,
                   TransparentBackground=0)
    print("  wrote", path)


def slice_view(src, origin, normal, out, edges=True, camera=None, zoom=1.0):
    view = new_view()
    sl = Slice(Input=src)
    sl.SliceType = "Plane"
    sl.SliceType.Origin = list(origin)
    sl.SliceType.Normal = list(normal)
    d = Show(sl, view)
    d.Representation = "Surface With Edges" if edges else "Surface"
    d.ColorArrayName = [None, ""]
    d.AmbientColor = list(EDGE)
    d.DiffuseColor = [0.80, 0.83, 0.87]
    d.EdgeColor = list(EDGE)
    d.LineWidth = 1.0
    view.InteractionMode = "2D"
    ResetCamera(view)
    if camera:
        view.CameraPosition = camera[0]
        view.CameraFocalPoint = camera[1]
        view.CameraViewUp = camera[2]
    view.CameraParallelScale = view.CameraParallelScale / zoom
    save(view, out)
    Delete(sl)
    Delete(view)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    case = os.path.abspath(args.case)
    out = os.path.abspath(args.out or os.path.join(case, "mesh_images"))
    os.makedirs(out, exist_ok=True)
    print("rendering", case, "->", out)

    src = load(case)

    # -- 1. exterior, coloured by patch ------------------------------------
    view = new_view()
    for name, rgb in PATCH_RGB.items():
        blk = extract_patch(src, name)
        d = Show(blk, view)
        d.Representation = "Surface"
        d.ColorArrayName = [None, ""]
        d.DiffuseColor = list(rgb)
        d.AmbientColor = list(rgb)
        # hood/walls translucent so the tray and ports read through them
        d.Opacity = 0.22 if name in ("hood", "walls", "floor") else 1.0
    ResetCamera(view)
    view.CameraPosition = [0.34, -0.26, 0.24]
    view.CameraFocalPoint = [0.06, 0.0933, 0.055]
    view.CameraViewUp = [0.0, 0.0, 1.0]
    save(view, os.path.join(out, "01_patches.png"))
    Delete(view)

    # -- 2-4. orthogonal cuts through the mesh -----------------------------
    # mid-width: hood profile + tray + vertical stack-up
    slice_view(src, (0.060, 0, 0), (1, 0, 0),
               os.path.join(out, "02_slice_x.png"),
               camera=([0.5, 0.0933, 0.0717], [0.06, 0.0933, 0.0717],
                       [0, 0, 1]))
    # mid-depth: the tray side slots
    slice_view(src, (0, 0.0933, 0), (0, 1, 0),
               os.path.join(out, "03_slice_y.png"),
               camera=([0.06, -0.4, 0.0717], [0.06, 0.0933, 0.0717],
                       [0, 0, 1]))
    # port centreline: the jet path down the chamber
    slice_view(src, (0, 0, 0.066667), (0, 0, 1),
               os.path.join(out, "04_slice_z.png"),
               camera=([0.06, 0.0933, 0.5], [0.06, 0.0933, 0.066667],
                       [0, 1, 0]))

    # -- 5. close-up of the tray/wall junction ------------------------------
    # RETARGETED 2026-08-16. This used to frame a 2.5 mm tray side slot, the
    # tightest feature in the mesh. The flush tray has no slots, so the feature
    # worth checking by eye is now the CONCAVE CORNER where the tray top meets
    # the side wall: since the tray went from nSurfaceLayers 0 to 4, two layer
    # stacks collide there, and a concave corner is where layer collapse and
    # sliver cells show up first.
    #
    # What good looks like: 4 layers running along the tray top, 4 up the wall,
    # meeting without either stack pinching out or folding. checkMesh's layer
    # coverage summary is the number; this is the picture behind it.
    view = new_view((900, 1300))     # portrait: the layer stack is thin and tall
    sl = Slice(Input=src)
    sl.SliceType = "Plane"
    sl.SliceType.Origin = [0, 0.0933, 0]
    sl.SliceType.Normal = [0, 1, 0]
    d = Show(sl, view)
    d.Representation = "Surface With Edges"
    d.ColorArrayName = [None, ""]
    d.DiffuseColor = [0.80, 0.83, 0.87]
    d.EdgeColor = list(EDGE)
    d.LineWidth = 1.4
    view.InteractionMode = "2D"
    view.CameraPosition = [0.008, -0.4, 0.027]
    view.CameraFocalPoint = [0.008, 0.0933, 0.027]
    view.CameraViewUp = [0, 0, 1]
    # 24 mm tall x 16.6 mm wide, centred on the junction: enough tray top and
    # enough wall on either side of the corner to see both layer stacks resolve.
    view.CameraParallelScale = 0.012
    save(view, os.path.join(out, "05_tray_wall_junction.png"))
    Delete(sl)
    Delete(view)

    # -- 6. 3D cutaway: the mesh on an interior cut, in context -------------
    view = new_view()
    clip = Clip(Input=src)
    clip.ClipType = "Plane"
    clip.ClipType.Origin = [0, 0.0933, 0]
    # Keep the FAR half (y > mid-depth) so the camera at y < 0 looks straight
    # at the cut face. Getting this backwards renders the intact outside.
    clip.ClipType.Normal = [0, 1, 0]
    clip.Invert = 0
    d = Show(clip, view)
    d.Representation = "Surface With Edges"
    d.ColorArrayName = [None, ""]
    d.DiffuseColor = [0.78, 0.81, 0.86]
    d.EdgeColor = [0.12, 0.13, 0.16]
    d.LineWidth = 0.6
    d.Opacity = 1.0
    ResetCamera(view)
    view.CameraPosition = [0.30, -0.30, 0.20]
    view.CameraFocalPoint = [0.06, 0.093, 0.060]
    view.CameraViewUp = [0, 0, 1]
    save(view, os.path.join(out, "06_cutaway.png"))

    print("done")


if __name__ == "__main__":
    main()
