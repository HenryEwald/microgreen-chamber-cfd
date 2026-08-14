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
BOUNDARY_DS = 0.001      # vertex spacing on the cross-section boundary (1 mm),
#                          chosen to match the port ring (2*pi*10/64 = 0.98 mm)
#                          and the hood profile (152.8/200 = 0.76 mm)

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


def samples(a, b, ds):
    """Evenly spaced values from a to b inclusive, step <= ds."""
    n = max(1, int(math.ceil(abs(b - a) / ds)))
    return [a + (b - a) * i / n for i in range(n + 1)]


def cross_section(profile, xs, zsL, zsR):
    """Closed CCW polygon of the chamber cross-section in the (x, z) plane.

    Floor, up the right wall, back along the hood, down the left wall.

    The straight edges are DENSIFIED to roughly the same vertex spacing as the
    hood profile and the port ring. Two reasons, both load-bearing:

      * the end wall is triangulated by zipping this loop against the port ring
        (write_end_wall). If the loop were four long edges, every ring vertex in
        a sector would fan back to one distant corner and the annulus would come
        out as ~70:1 slivers.
      * the floor / side walls / hood are built from exactly these same sample
        points, so the end wall shares every boundary vertex with its
        neighbours. That is what makes the shell watertight -- inserting points
        on the end wall that the adjoining surfaces do not have leaves a
        T-junction and an open edge on every one of them.

    The region is CONVEX (a rectangle capped by a concave curve) and the port
    centre is strictly inside it, so angles about the port centre increase
    monotonically along this loop. write_end_wall relies on that.
    """
    poly = [(x, 0.0) for x in xs]                          # floor, left -> right
    poly += [(WIDTH, z) for z in zsR[1:]]                  # right wall, up
    poly += [(x, z) for x, z in reversed(profile[:-1])]    # hood, right -> left
    poly += [(0.0, z) for z in reversed(zsL[1:-1])]        # left wall, down
    return poly


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
# Both loops are star-shaped about the port centre and are given CCW, so the
# angle about that centre increases monotonically along each. That reduces the
# annulus to a two-pointer merge ("zip"): walk both loops together in angle
# order, at each step advancing whichever is behind and emitting one triangle.
#
# Every outer edge and every ring edge is consumed exactly once and NO new
# vertices are introduced, so the wall is watertight against its neighbours by
# construction -- which is precisely what the previous ray-casting version got
# wrong.
# ---------------------------------------------------------------------------
def _unwrap(p, a0):
    """Angle of p about the port centre, measured CCW from a0, in [0, 2*pi)."""
    return (math.atan2(p[1] - PORT_Z, p[0] - PORT_X) - a0) % TWO_PI


def write_end_wall(f, y, reverse, poly, ring):
    """Triangulate the pierced end wall at y.

    `reverse` flips the winding. A triangle wound CCW in the (x, z) plane has
    normal -y, which is outward at y = 0; the wall at y = DEPTH needs the
    opposite.
    """
    a0 = math.atan2(poly[0][1] - PORT_Z, poly[0][0] - PORT_X)
    uo = [_unwrap(p, a0) for p in poly]
    uo[0] = 0.0

    # rotate the ring so its unwrapped angles are ascending too
    ur = [_unwrap(p, a0) for p in ring]
    k = min(range(len(ring)), key=lambda i: ur[i])
    ring = ring[k:] + ring[:k]
    ur = ur[k:] + ur[:k]

    N, M = len(poly), len(ring)

    def to3(p):
        return (p[0], y, p[1])

    def emit(a, b, c):
        return facet(f, a, c, b) if reverse else facet(f, a, b, c)

    written = 0
    i = j = 0
    while i < N or j < M:
        nxt_o = uo[i + 1] if i + 1 < N else TWO_PI
        nxt_r = ur[j + 1] if j + 1 < M else TWO_PI
        if j >= M or (i < N and nxt_o <= nxt_r):
            # consume one outer edge
            written += emit(to3(poly[i]), to3(poly[(i + 1) % N]),
                            to3(ring[j % M]))
            i += 1
        else:
            # consume one ring edge (traversed CW as seen from the annulus)
            written += emit(to3(poly[i % N]), to3(ring[(j + 1) % M]),
                            to3(ring[j % M]))
            j += 1
    return written


# ---------------------------------------------------------------------------
def write_chamber(path, profile, ds=BOUNDARY_DS):
    """Write the closed fluid-domain shell. Normals point OUT of the fluid."""
    ring = port_ring(PORT_SEGMENTS)
    zL, zR = profile[0][1], profile[-1][1]

    # Shared boundary samples. The end walls, the floor, the side walls and the
    # hood all key off these, so every seam has matching vertices on both sides.
    xs = samples(0.0, WIDTH, ds)
    zsL = samples(0.0, zL, ds)
    zsR = samples(0.0, zR, ds)
    poly = cross_section(profile, xs, zsL, zsR)

    nf = 0
    with open(path, "w") as f:
        f.write("solid floor\n")
        for i in range(len(xs) - 1):
            nf += quad(f, (xs[i], 0, 0), (xs[i], DEPTH, 0),
                       (xs[i + 1], DEPTH, 0), (xs[i + 1], 0, 0))
        f.write("endsolid floor\n")

        f.write("solid walls\n")
        for i in range(len(zsL) - 1):                      # x = 0, normal -x
            nf += quad(f, (0, 0, zsL[i]), (0, 0, zsL[i + 1]),
                       (0, DEPTH, zsL[i + 1]), (0, DEPTH, zsL[i]))
        for i in range(len(zsR) - 1):                      # x = WIDTH, normal +x
            nf += quad(f, (WIDTH, 0, zsR[i]), (WIDTH, DEPTH, zsR[i]),
                       (WIDTH, DEPTH, zsR[i + 1]), (WIDTH, 0, zsR[i + 1]))
        nf += write_end_wall(f, 0.0, False, poly, ring)    # normal -y
        nf += write_end_wall(f, DEPTH, True, poly, ring)   # normal +y
        f.write("endsolid walls\n")

        f.write("solid hood\n")
        for i in range(len(profile) - 1):
            x0, z0 = profile[i]
            x1, z1 = profile[i + 1]
            nf += quad(f, (x0, 0, z0), (x1, 0, z1),
                       (x1, DEPTH, z1), (x0, DEPTH, z0))
        f.write("endsolid hood\n")

        # Port caps close the shell. Same outward convention as the end wall
        # they sit in: -y at the inlet, +y at the outlet.
        for name, y, reverse in (("inlet", 0.0, False), ("outlet", DEPTH, True)):
            f.write("solid %s\n" % name)
            c = (PORT_X, y, PORT_Z)
            for i in range(PORT_SEGMENTS):
                a = (ring[i][0], y, ring[i][1])
                b = (ring[(i + 1) % PORT_SEGMENTS][0], y,
                     ring[(i + 1) % PORT_SEGMENTS][1])
                nf += facet(f, c, b, a) if reverse else facet(f, c, a, b)
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
def verify_closed(path, expect_volume=None):
    """Check the surface is safe to hand to snappyHexMesh.

    Three independent checks, because closure alone is not enough:

      1. CLOSED    -- every edge shared by exactly two facets. A hole lets
                      snappy leak out of the domain and mesh the whole
                      background block.
      2. ORIENTED  -- every edge traversed once in each direction. Catches a
                      patch whose winding is inverted relative to its
                      neighbours, which closure cannot see.
      3. VOLUME    -- signed volume by the divergence theorem. Positive means
                      the normals point OUT; the magnitude cross-checks the
                      geometry against the numbers in report().
    """
    half = defaultdict(int)
    verts, nf, vol = [], 0, 0.0
    with open(path) as f:
        for line in f:
            s = line.split()
            if s and s[0] == "vertex":
                verts.append(tuple(round(float(v), 9) for v in s[1:4]))
                if len(verts) == 3:
                    nf += 1
                    a, b, c = verts
                    vol += (a[0] * (b[1] * c[2] - b[2] * c[1])
                            - a[1] * (b[0] * c[2] - b[2] * c[0])
                            + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
                    for i in range(3):
                        half[(verts[i], verts[(i + 1) % 3])] += 1
                    verts = []

    unmatched = [e for e in half if half[(e[1], e[0])] != half[e]]
    dup = [e for e, n in half.items() if n != 1]
    closed = not unmatched and not dup

    msgs = []
    msgs.append("CLOSED+ORIENTED" if closed else
                "BAD (%d unmatched, %d duplicated half-edges)"
                % (len(unmatched), len(dup)))
    msgs.append("vol %+8.4f L" % (vol * 1e3))
    ok = closed and vol > 0
    if vol <= 0:
        msgs.append("<- NEGATIVE: normals point INTO the solid")
    if expect_volume is not None:
        err = abs(vol - expect_volume)
        msgs.append("(expect %.4f, err %.2e L)" % (expect_volume * 1e3, err * 1e3))
        if err > 1e-6:                      # 1 mL
            ok = False
            msgs.append("<- VOLUME MISMATCH")

    print("  %-14s %6d facets  %s" % (os.path.basename(path), nf, "  ".join(msgs)))
    return ok


def report(profile):
    area = arc = 0.0
    for i in range(len(profile) - 1):
        dx = profile[i + 1][0] - profile[i][0]
        area += dx * ((profile[i][1] - BOX_H) + (profile[i + 1][1] - BOX_H)) / 2
        arc += math.hypot(dx, profile[i + 1][1] - profile[i][1])
    hood_v = area * DEPTH
    box_v = WIDTH * BOX_H * DEPTH
    tray_v = TRAY_W * TRAY_H * TRAY_D
    shell_v = box_v + hood_v            # what chamber.stl encloses (no tray)
    v_air = shell_v - tray_v
    print("  hood apex            %8.4f cm   (expect 14.3334)" % (max(p[1] for p in profile) * 100))
    print("  internal lip height  %8.4f cm   (expect  0.394)" % ((profile[0][1] - BOX_H) * 100))
    print("  hood x-section       %8.4f cm2  (expect 38.80)" % (area * 1e4))
    print("  hood arc length      %8.4f cm   (expect 15.28)" % (arc * 100))
    print("  V_air                %8.4f L    (expect  2.530)" % (v_air * 1e3))
    # v_air is in m3. ACH = Q / V_air with Q in m3/h; tau = V_air / Q in seconds.
    print("  ACH @ 5 m3/h         %8.0f h-1  tau %.2f s   (expect 1976, 1.82)" %
          (5.0 / v_air, 3600.0 * v_air / 5.0))
    return shell_v, tray_v


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
    shell_v, tray_v = report(profile)

    if args.verify:
        ok = verify_closed(chamber, shell_v) & verify_closed(tray, tray_v)
        if not ok:
            raise SystemExit("surface failed verification -- do not mesh with this")


if __name__ == "__main__":
    main()
