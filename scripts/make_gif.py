#!/usr/bin/env python3
"""Assemble rendered frames into an animated GIF.

    python3 scripts/make_gif.py doc/animation [--fps 12] [--out flow.gif]

There is no ffmpeg or ImageMagick on this machine (checked 2026-08-15), so
Pillow writes the GIF directly. That caps quality at 256 colours per frame,
which is fine for a sequential-colormap field render and poor for photographs.

If a real video is wanted later, the frames are already on disk as PNGs and any
encoder can take them:  ffmpeg -framerate 12 -i frame_%04d.png out.mp4
"""

import argparse
import glob
import os

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--fps", type=float, default=12)
    ap.add_argument("--out", default=None)
    ap.add_argument("--loop", type=int, default=0, help="0 = forever")
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, "frame_*.png")))
    if not files:
        raise SystemExit(f"no frame_*.png in {a.dir}")

    out = a.out or os.path.join(a.dir, "animation.gif")
    frames = []
    for f in files:
        im = Image.open(f).convert("RGB")
        if a.scale != 1.0:
            im = im.resize((int(im.width * a.scale), int(im.height * a.scale)),
                           Image.LANCZOS)
        # Palettise per frame with dithering off: a smooth sequential ramp
        # dithers into visible noise that reads as spurious turbulence.
        frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=256,
                                 dither=Image.NONE))

    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=int(1000 / a.fps), loop=a.loop, optimize=True)
    mb = os.path.getsize(out) / 1e6
    print(f"wrote {out}  ({len(frames)} frames, {a.fps:g} fps, "
          f"{len(frames)/a.fps:.1f} s, {mb:.1f} MB)")


if __name__ == "__main__":
    main()
