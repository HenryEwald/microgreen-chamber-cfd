#!/usr/bin/env python3
"""
Generate the microgreen chamber internal geometry as STL surfaces.

The chamber is fully analytic (CLAUDE.md 6.1) -- there is no CAD input. This
script is the single source of geometric truth; snappyHexMesh consumes its
output.

Writes into <case>/constant/triSurface/:
    chamber.stl   closed shell of the fluid domain, multi-solid:
                  floor / walls / hood / inlet / outlet
    tray.stl      closed box, solid: tray

Coordinate system (metres, origin at the internal floor, front-left corner):
    x  0 -> 0.120000   chamber width      (ports are centred on this)
    y  0 -> 0.186667   chamber depth      (inlet at y=0, outlet at y=depth)
    z  0 -> 0.143334   floor to hood apex

Hood: the sketch gives the EXTERNAL profile as a parabola,

    y_ext(x) = RISE * [ 1 - ((x - A)/A)^2 ]        above the lip line

and the internal surface is its true normal offset inward by the wall thickness.
That offset is NOT a parabola -- fitting one is wrong by 1.06 mm at the
springing, and the error does not shrink under refinement (CLAUDE.md 6.1). It is
computed numerically here instead.

Self-check: run with --verify to check the emitted surfaces are closed (every
edge shared by exactly two facets) before handing them to snappy.

Usage:
    python3 make_geometry.py --case <case-dir> [--profile-points 200] [--verify]
"""

import argparse
import math
import os
from collections import defaultdict

# ---------------------------------------------------------------------------
# Chamber parameters -- CLAUDE.md 6.1. Metres.
# ---------------------------------------------------------------------------
WALL = 0.0033333         # wall / floor / hood shell thickness (3.333 mm)

WIDTH = 0.120000         # internal, x
DEPTH = 0.186667         # internal, y
BOX_H = 0.096667         # internal floor -> hood spring line, z

LIP = 0.005              # external lip height above the spring line
RISE = 0.045             # external parabola rise above the lip line
A = 0.063335             # external parabola half-span (= external width / 2)

PORT_R = 0.010           # port radius
PORT_X = 0.060           # port centre, x (centred on width)
PORT_Z = 0.066667        # port centre, z above the internal floor
#                          = 0.060 external + 0.010 - 0.0033333 floor

TRAY_W, TRAY_H, TRAY_D = 0.115, 0.025, 0.125
TRAY_X0 = (WIDTH - TRAY_W) / 2.0          # 0.0025
TRAY_Y0 = (DEPTH - TRAY_D) / 2.0          # 0.0308335
TRAY_X1, TRAY_Y1 = TRAY_X0 + TRAY_W, TRAY_Y0 + TRAY_D

PORT_SEGMENTS = 64       # tessellation of the circular port openings

TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Hood profile
# ---------------------------------------------------------------------------
def hood_profile(n):
    """Internal hood profile as (x, z) from the left wall to the right wall.

    True normal offset of the external parabola, clipped to the internal span.
    The offset curve meets the side wall BELOW the external lip top (z ~ 0.100608
    => internal lip 3.94 mm, not 5 mm), so the caller closes it with vertical
    segments down to BOX_H.
    """
    z_lip = BOX_H + LIP
    raw = []
    m = max(20 * n, 20000)
    for i in range(m + 1):
        xe = 2.0 * A * i / m
        dy = -2.0 * RISE * (xe - A) / (A * A)
        nrm = math.sqrt(1.0 + dy * dy)
        ye = RISE * (1.0 - ((xe - A) / A) ** 2)
        xi = xe + WALL * dy / nrm - WALL      # inward normal (dy,-1)/|.|, then
        zi = z_lip + ye - WALL / nrm          # external x -> internal x
        if -1e-12 <= xi <= WIDTH + 1e-12:
            raw.append((min(max(xi, 0.0), WIDTH), zi))

    # resample evenly in arc length so the STL facets are well conditioned
    cum = [0.0]
    for i in range(1, len(raw)):
        cum.append(cum[-1] + math.hypot(raw[i][0] - raw[i - 1][0],
                                        raw[i][1] - raw[i - 1][1]))
    total, out, j = cum[-1], [], 0
    for i in range(n + 1):
        target = total * i / n
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        span = cum[j + 1] - cum[j]
        f = 0.0 if span <= 0 else (target - cum[j]) / span
        out.append((raw[j][0] + f * (raw[j + 1][0] - raw[j][0]),
                    raw[j][1] + f * (raw[j + 1][1] - raw[j][1])))
    out[0] = (0.0, out[0][1])
    out[-1] = (WIDTH, out[-1][1])
    return out


def cross_section(profile):
    """Closed CCW polygon of the chamber cross-section in the (x, z) plane.

    Floor, up the right wall, back along the hood, down the left wall. The
    region is CONVEX (a rectangle capped by a concave curve), which is what
    makes the star-shaped triangulation below valid.
    """
    poly = [(0.0, 0.0), (WIDTH, 0.0), (WIDTH, profile[-1][1])]
    poly += [(x, z) for x, z in reversed(profile[1:-1])]
    poly += [(0.0, profile[0][1])]
    # drop duplicates
    clean = [poly[0]]
    for p in poly[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-12:
            clean.append(p)
    return clean


# ---------------------------------------------------------------------------
# STL primitives.  Normals point OUT of the fluid domain.
# ---------------------------------------------------------------------------
def facet(f, a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    mag = math.sqrt(nx * nx + ny * ny + nz * nz)
    if mag < 1e-20:
        return 0                      # degenerate, skip
    nx, ny, nz = nx / mag, ny / mag, nz / mag
    f.write("  facet normal %.9e %.9e %.9e\n    outer loop\n" % (nx, ny, nz))
    for p in (a, b, c):
        f.write("      vertex %.9e %.9e %.9e\n" % (p[0], p[1], p[2]))
    f.write("    endloop\n  endfacet\n")
    return 1


def quad(f, a, b, c, d):
    return facet(f, a, b, c) + facet(f, a, c, d)


def port_ring(n):
    return [(PORT_X + PORT_R * math.cos(TWO_PI * i / n),
             PORT_Z + PORT_R * math.sin(TWO_PI * i / n)) for i in range(n)]


# ---------------------------------------------------------------------------
# End wall: convex polygon with a circular hole.
#
# The cross-section is convex, so it is star-shaped about the port centre. That
# lets us build a watertight annulus without a general polygon triangulator:
#
#   1. cast a ray from the port centre through every ring vertex onto the
#      polygon boundary  -> one outer point per ring vertex, at the same angle
#   2. merge those with the polygon's own vertices and sort by angle
#   3. walk the merged loop, fanning each outer edge back to the ring vertex
#      that currently "owns" that angular sector, and closing the sector when
#      the owner advances
#
# Every outer edge and every ring edge is used exactly once, so the result is
# closed by construction.
# ---------------------------------------------------------------------------
def _ang(p):
    return math.atan2(p[1] - PORT_Z, p[0] - PORT_X) % TWO_PI


def _ray_hit(poly, dx, dz):
    """First boundary hit of the ray from the port centre in direction (dx,dz)."""
    best = None
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        ex, ez = x2 - x1, z2 - z1
        den = dx * ez - dz * ex
        if abs(den) < 1e-18:
            continue
        rx, rz = x1 - PORT_X, z1 - PORT_Z
        t = (rx * ez - rz * ex) / den        # along the ray
        u = (rx * dz - rz * dx) / den        # along the edge
        if t > 1e-12 and -1e-9 <= u <= 1 + 1e-9:
            if best is None or t < best:
                best = t
    if best is None:
        raise RuntimeError("ray from port centre escaped the cross-section -- "
                           "the port does not lie inside the wall")
    return (PORT_X + best * dx, PORT_Z + best * dz)


def write_end_wall(f, y, flip, poly, ring):
    nr = len(ring)

    merged = []
    for i, r in enumerate(ring):
        q = _ray_hit(poly, r[0] - PORT_X, r[1] - PORT_Z)
        merged.append((_ang(r), q, i))
    for p in poly:
        merged.append((_ang(p), p, None))
    merged.sort(key=lambda t: (t[0], 0 if t[2] is not None else 1))

    # rotate so the loop starts on a ring-owned entry
    start = next(k for k, t in enumerate(merged) if t[2] is not None)
    merged = merged[start:] + merged[:start]

    def to3(p):
        return (p[0], y, p[1])

    written, owner = 0, merged[0][2]
    n = len(merged)
    for k in range(n):
        _, qa, _ = merged[k]
        _, qb, ib = merged[(k + 1) % n]
        r_own = to3(ring[owner])
        if flip:
            written += facet(f, r_own, to3(qb), to3(qa))
        else:
            written += facet(f, r_own, to3(qa), to3(qb))
        if ib is not None:                       # sector handover
            if flip:
                written += facet(f, r_own, to3(ring[ib]), to3(qb))
            else:
                written += facet(f, r_own, to3(qb), to3(ring[ib]))
            owner = ib
    return written


# ---------------------------------------------------------------------------
def write_chamber(path, profile):
    ring = port_ring(PORT_SEGMENTS)
    poly = cross_section(profile)
    zL, zR = profile[0][1], profile[-1][1]
    nf = 0
    with open(path, "w") as f:
        f.write("solid floor\n")
        nf += quad(f, (0, 0, 0), (0, DEPTH, 0), (WIDTH, DEPTH, 0), (WIDTH, 0, 0))
        f.write("endsolid floor\n")

        f.write("solid walls\n")
        nf += quad(f, (0, 0, 0), (0, 0, zL), (0, DEPTH, zL), (0, DEPTH, 0))
        nf += quad(f, (WIDTH, 0, 0), (WIDTH, DEPTH, 0),
                   (WIDTH, DEPTH, zR), (WIDTH, 0, zR))
        nf += write_end_wall(f, 0.0, True, poly, ring)
        nf += write_end_wall(f, DEPTH, False, poly, ring)
        f.write("endsolid walls\n")

        f.write("solid hood\n")
        for i in range(len(profile) - 1):
            x0, z0 = profile[i]
            x1, z1 = profile[i + 1]
            nf += quad(f, (x0, 0, z0), (x1, 0, z1),
                       (x1, DEPTH, z1), (x0, DEPTH, z0))
        f.write("endsolid hood\n")

        for name, y, flip in (("inlet", 0.0, True), ("outlet", DEPTH, False)):
            f.write("solid %s\n" % name)
            c = (PORT_X, y, PORT_Z)
            for i in range(PORT_SEGMENTS):
                a = (ring[i][0], y, ring[i][1])
                b = (ring[(i + 1) % PORT_SEGMENTS][0], y,
                     ring[(i + 1) % PORT_SEGMENTS][1])
                nf += facet(f, c, b, a) if flip else facet(f, c, a, b)
            f.write("endsolid %s\n" % name)
    return nf


def write_tray(path):
    x0, x1, y0, y1, z0, z1 = TRAY_X0, TRAY_X1, TRAY_Y0, TRAY_Y1, 0.0, TRAY_H
    with open(path, "w") as f:
        f.write("solid tray\n")
        # normals point out of the tray solid, i.e. into the fluid
        quad(f, (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))
        quad(f, (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0))
        quad(f, (x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))
        quad(f, (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0))
        quad(f, (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0))
        quad(f, (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))
        f.write("endsolid tray\n")


# ---------------------------------------------------------------------------
def verify_closed(path):
    """Every edge must be shared by exactly two facets, or snappy will leak."""
    edges = defaultdict(int)
    verts, nf = [], 0
    with open(path) as f:
        for line in f:
            s = line.split()
            if s and s[0] == "vertex":
                verts.append(tuple(round(float(v), 9) for v in s[1:4]))
                if len(verts) == 3:
                    nf += 1
                    for i in range(3):
                        a, b = verts[i], verts[(i + 1) % 3]
                        edges[(a, b) if a < b else (b, a)] += 1
                    verts = []
    bad = {e: c for e, c in edges.items() if c != 2}
    status = "CLOSED" if not bad else "NOT CLOSED (%d bad edges)" % len(bad)
    print("  %-14s %6d facets  %s" % (os.path.basename(path), nf, status))
    return not bad


def report(profile):
    area = arc = 0.0
    for i in range(len(profile) - 1):
        dx = profile[i + 1][0] - profile[i][0]
        area += dx * ((profile[i][1] - BOX_H) + (profile[i + 1][1] - BOX_H)) / 2
        arc += math.hypot(dx, profile[i + 1][1] - profile[i][1])
    hood_v = area * DEPTH
    box_v = WIDTH * BOX_H * DEPTH
    tray_v = TRAY_W * TRAY_H * TRAY_D
    v_air = box_v + hood_v - tray_v
    print("  hood apex            %8.4f cm   (expect 14.3334)" % (max(p[1] for p in profile) * 100))
    print("  internal lip height  %8.4f cm   (expect  0.394)" % ((profile[0][1] - BOX_H) * 100))
    print("  hood x-section       %8.4f cm2  (expect 38.80)" % (area * 1e4))
    print("  hood arc length      %8.4f cm   (expect 15.28)" % (arc * 100))
    print("  V_air                %8.4f L    (expect  2.530)" % (v_air * 1e3))
    print("  ACH @ 5 m3/h         %8.0f h-1  tau %.2f s" %
          (5.0 / (v_air * 1000), 3600 * v_air * 1000 / 5.0))
    return v_air


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--profile-points", type=int, default=200)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    out = os.path.join(args.case, "constant", "triSurface")
    os.makedirs(out, exist_ok=True)

    profile = hood_profile(args.profile_points)
    chamber = os.path.join(out, "chamber.stl")
    tray = os.path.join(out, "tray.stl")
    write_chamber(chamber, profile)
    write_tray(tray)
    print("wrote %s (%d profile points)" % (out, args.profile_points))
    report(profile)

    if args.verify:
        ok = verify_closed(chamber) & verify_closed(tray)
        if not ok:
            raise SystemExit("surface is not closed -- do not mesh with this")


if __name__ == "__main__":
    main()
