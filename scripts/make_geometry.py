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

# Port radius. Was a fixed 0.010 (Oe 20 mm) until 2026-08-16; it is now set from
# --port-r because the fan change (LD3007MS -> Sunon MF50100V2) moves the
# operating point strongly with port area: the system loss goes as D^-4, so
# Oe 20 -> Oe 40 takes the delivered flow from 4.25 to 11.8 m3/h against the same
# 27.4 Pa shut-off. See CLAUDE.md 6.2.
PORT_R = 0.020           # port radius -- DEFAULT IS NOW Oe 40 mm
PORT_X = 0.060           # port centre, x (centred on width)
PORT_Z = 0.066667        # port centre, z above the internal floor
#                          = 0.060 external + 0.010 - 0.0033333 floor
#
# NOTE the centre is UNCHANGED by the port enlargement -- only the radius grows,
# symmetrically about z = 66.667 mm. At Oe 40 that spans z = 46.7 .. 86.7 mm:
# 21.7 mm clear above the tray top and 10.0 mm below the hood spring line. Oe 50
# would leave only 5.0 mm, and Oe 55 breaks out of the box section entirely.

# ---------------------------------------------------------------------------
# Inlet vane diffuser -- CLAUDE.md 6.2a. INLET ONLY.
#
# The chamber cannot be over-ventilated: reaching the 0.8 m/s ceiling in the
# bulk would need 35.9 m3/h, far beyond this fan at any port size, and at Oe 40
# U_bulk = 0.262 m/s against a 0.30 m/s target. So the only way to exceed the
# ceiling anywhere is a surviving jet core, and the only way to reach the target
# everywhere is piston-like flow. The diffuser's whole job is jet -> plug.
#
# It is HORIZONTAL TURNING VANES ONLY -- there is deliberately no lateral fan.
# The lateral spread needed is 12 deg (40 -> 120 mm over 187 mm) and a free jet
# already opens at ~12 deg half-angle, with a wall jet on the tray spreading
# faster still. Lateral turning buys nothing; downward tilt buys the one thing
# the flow will not do on its own, which is descend the 41.7 mm to the tray.
#
# An outlet is a sink -- potential-flow-like, no directional reach (CLAUDE.md
# 6.2) -- so it gets no diffuser.
DIFF_L      = 0.010      # shroud length into the chamber (5.4 % of DEPTH)
DIFF_EMBED  = 0.0005     # upstream rim buried in the end wall, see below
DIFF_RI     = 0.0205     # shroud inner radius: 0.5 mm CLEAR of the port bore
DIFF_RO     = 0.0220     # shroud outer radius (1.5 mm shell)
VANE_T      = 0.0015     # vane thickness -- printable at a 0.4 mm nozzle,
#                          ~3.6 cells across at snappy level 4 (0.417 mm at m0)
VANE_C      = 0.010      # vane chord, PROJECTED on y (solidity c/s = 1.5)
VANE_Y0     = 0.0005     # vane leading edge, 0.5 mm downstream of the inlet
#                          plane -- see the coincidence note below
VANE_LAP    = 0.00075    # vane end penetration into the shroud wall

# Two embeddings, both for the same reason the tray is written 1 mm oversize:
# coincident surfaces leave snappy's snap direction undefined, and both usual
# outcomes (a leak, or a zero-thickness sliver) pass checkMesh.
#
#   * the shroud rim runs from y = -DIFF_EMBED, so it CROSSES the end-wall plane
#     rather than terminating on it;
#   * the vane leading edge starts at y = +VANE_Y0, so it does not sit in the
#     plane of the inlet patch disc;
#   * the vane ends run VANE_LAP past the shroud inner surface, so they are
#     buried in the 1.5 mm shell instead of touching it tangentially.
#
# CONSEQUENCE, exactly as for tray.eMesh (CLAUDE.md 6.1): every vane root edge
# now lies INSIDE solid. `diffuser.eMesh` is therefore deliberately kept OUT of
# snappy's `features` list -- explicit feature snapping would drag mesh points
# onto those buried edges and grow a skirt, which is invisible to `Mesh OK` and
# shows up only in the total volume. Level-4 refinementSurfaces resolves the
# vanes without it.

# Tray. FLUSH WITH ALL FOUR CHAMBER WALLS as of 2026-08-16 (design change): it
# fills the whole internal floor footprint, so there are neither 2.5 mm side
# slots nor 3.08 cm end gaps. It was 0.115 x 0.025 x 0.125 m, centred.
#
# CONSEQUENCE, read this before interpreting any result: the tray now covers the
# floor completely, so the `floor` patch has NO fluid faces at all. The bottom of
# the fluid domain IS the tray top. The chamber floor is effectively raised to
# z = 25 mm and `floor` survives only as an empty patch.
TRAY_H = 0.025           # tray top above the internal floor -- the metric surface

# The tray is written 1 mm OVERSIZE in x, y and downward in z, so that its sides
# and base are buried in the wall/floor material instead of sitting exactly on
# them. Coincident surfaces are the one thing snappyHexMesh has no good answer
# for: two coplanar triangulations at x = 0 leave the snapping direction
# undefined, and the usual outcomes are a leak or a zero-thickness sliver, both
# of which pass checkMesh. Burying the faces makes every intersection
# transversal, which is the well-conditioned case.
#
# 1 mm < WALL (3.333 mm), so the oversize stays inside the shell material and
# never pokes out of the chamber's external surface.
#
# The TOP face is NOT offset -- z = TRAY_H exactly. It is a real fluid boundary
# and the surface every tray metric is evaluated on.
TRAY_EMBED = 0.001

TRAY_X0, TRAY_X1 = -TRAY_EMBED, WIDTH + TRAY_EMBED
TRAY_Y0, TRAY_Y1 = -TRAY_EMBED, DEPTH + TRAY_EMBED
TRAY_Z0, TRAY_Z1 = -TRAY_EMBED, TRAY_H

# Volume the tray STL encloses (what verify_closed measures) vs the volume it
# actually displaces from the fluid (what V_air needs). They differ by the
# embedding, so they are kept separate -- conflating them is how a 1 mm margin
# silently becomes a 1 mm geometry error.
TRAY_STL_V = ((TRAY_X1 - TRAY_X0) * (TRAY_Y1 - TRAY_Y0) * (TRAY_Z1 - TRAY_Z0))
TRAY_DISP_V = WIDTH * DEPTH * TRAY_H      # clipped to the internal footprint

BOUNDARY_DS = 0.001      # vertex spacing on the cross-section boundary (1 mm),
#                          matched by the port ring and the hood profile
#                          (152.8/200 = 0.76 mm)

# Tessellation of the circular port openings. DERIVED from the radius so the
# vertex spacing stays ~BOUNDARY_DS whatever the port size -- a fixed 64 was
# right at Oe 20 (2*pi*10/64 = 0.98 mm) but would give 1.96 mm at Oe 40, coarser
# than every surface the ring has to zip against in write_end_wall.
def port_segments(r=None):
    r = PORT_R if r is None else r
    return max(64, 4 * int(round(TWO_PI * r / BOUNDARY_DS / 4)))

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
    nseg = port_segments()
    ring = port_ring(nseg)
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
            for i in range(nseg):
                a = (ring[i][0], y, ring[i][1])
                b = (ring[(i + 1) % nseg][0], y,
                     ring[(i + 1) % nseg][1])
                nf += facet(f, c, b, a) if reverse else facet(f, c, a, b)
            f.write("endsolid %s\n" % name)
    return nf


def write_tray(path):
    x0, x1, y0, y1, z0, z1 = TRAY_X0, TRAY_X1, TRAY_Y0, TRAY_Y1, TRAY_Z0, TRAY_Z1
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
# Inlet vane diffuser
# ---------------------------------------------------------------------------
def camber(s, tilt, z0):
    """Point and unit normal on a vane camber line at fractional chord s.

    Circular arc: the turn angle grows linearly with arc length, phi = tilt*s,
    so the tangent is (cos phi, -sin phi) in (y, z) and integrating it gives a
    circular arc. The arc length is scaled so the chord PROJECTED on y is
    exactly VANE_C whatever the tilt -- otherwise a steeper vane would also be a
    shorter one and the screen would confound tilt with solidity.

    Returns (y, z, ny, nz) with (ny, nz) the unit normal, +ve towards the
    suction (upper) side.
    """
    if tilt < 1e-9:
        return VANE_Y0 + VANE_C * s, z0, 0.0, 1.0
    L = VANE_C * tilt / math.sin(tilt)          # arc length for a VANE_C y-chord
    phi = tilt * s
    return (VANE_Y0 + L * math.sin(phi) / tilt,
            z0 - L * (1.0 - math.cos(phi)) / tilt,
            math.sin(phi), math.cos(phi))


def vane_halfwidth(z):
    """Vane half-span at height z: the shroud chord there, plus the overlap.

    Follows the shroud rather than staying constant, because a tilted vane
    DESCENDS along its chord -- at 45 deg the drop is 4.1 mm. A constant span
    set at the leading edge would push the trailing edge of the lowest vane
    ~5.6 mm outside the shroud, i.e. a plate hanging in open fluid.
    """
    d = abs(z - PORT_Z)
    return math.sqrt(max(DIFF_RI * DIFF_RI - d * d, 0.0)) + VANE_LAP


def vane_z_positions(n):
    """Vane leading-edge heights, evenly pitched across the port bore."""
    pitch = 2.0 * PORT_R / (n + 1)
    return [PORT_Z + (k - (n - 1) / 2.0) * pitch for k in range(n)]


def write_thick_body(f, up, lo):
    """Close a plate given its two offset surfaces as (ns+1) x (nu+1) grids.

    Shared by BOTH diffuser types. The winding here is the whole reason this is
    one function rather than two: each cap must traverse its shared edge
    OPPOSITE to the face it closes, or that half-edge is emitted twice in the
    same direction and the body reads as open while looking perfectly fine. The
    top face lays down up[0][j] -> up[0][j+1] along the leading edge, so the cap
    must lay down up[0][j+1] -> up[0][j], and so on round all four sides.
    """
    ns, nu = len(up) - 1, len(up[0]) - 1
    nf = 0
    for i in range(ns):
        for j in range(nu):
            nf += quad(f, up[i][j], up[i][j + 1], up[i + 1][j + 1], up[i + 1][j])
            nf += quad(f, lo[i][j], lo[i + 1][j], lo[i + 1][j + 1], lo[i][j + 1])
    for j in range(nu):                                    # leading edge cap
        nf += quad(f, up[0][j + 1], up[0][j], lo[0][j], lo[0][j + 1])
    for j in range(nu):                                    # trailing edge cap
        nf += quad(f, up[ns][j], up[ns][j + 1], lo[ns][j + 1], lo[ns][j])
    for i in range(ns):                                    # both span-end caps
        nf += quad(f, up[i][0], up[i + 1][0], lo[i + 1][0], lo[i][0])
        nf += quad(f, up[i + 1][nu], up[i][nu], lo[i][nu], lo[i + 1][nu])
    return nf


def write_vane(f, z0, tilt, ns=16, nu=28):
    """One closed cascade vane. Normals point OUT of the solid, into the fluid."""
    up, lo = [], []
    for i in range(ns + 1):
        s = i / ns
        y, z, ny, nz = camber(s, tilt, z0)
        hw = vane_halfwidth(z)
        rowu, rowl = [], []
        for j in range(nu + 1):
            u = -hw + 2.0 * hw * j / nu
            rowu.append((PORT_X + u, y + ny * VANE_T / 2, z + nz * VANE_T / 2))
            rowl.append((PORT_X + u, y - ny * VANE_T / 2, z - nz * VANE_T / 2))
        up.append(rowu)
        lo.append(rowl)
    return write_thick_body(f, up, lo)


# ---------------------------------------------------------------------------
# Radial (swirl) diffuser -- the alternative concept, CLAUDE.md 6.2a.
#
# Vanes radiate from a central hub, each CAMBERED from axial at the leading edge
# to RAD_ALPHA at the trailing edge, imparting swirl. This is the HVAC ceiling
# diffuser in doc/diffuser/concepts.png panel A, sized down.
#
# Two things are deliberately NOT copied from the full-size original:
#
#  1. VANE COUNT. A 300-600 mm diffuser carries ~24 vanes. At Oe 40 that would
#     block the hub root almost solid -- the tangential space per vane is
#     2*pi*r/N, so at r = 6 mm and 40 deg cant, 24 vanes of 1 mm block 83 % of
#     it. 12 vanes gives 42 % at the root and 13 % at the rim, which is what a
#     diffuser this size can actually be.
#  2. FLAT BLADES. The flow arrives AXIALLY from the port, so a flat plate set
#     at 40 deg would sit at 40 deg incidence and stall. The camber turns it
#     from 0 to alpha along the chord, exactly as the cascade vanes do -- the
#     difference is only which plane the turning happens in.
#
# Swirl number S = (2/3) tan(alpha) (1-h^3)/(1-h^2), h = hub/tip radius ratio.
# ABOVE S ~ 0.6 swirl breaks down into a central recirculation bubble. In an
# open room that IS the mixing mechanism; in a closed 2.3 L box it is a standing
# recirculation, i.e. re-breathing -- the same failure as the short-circuiting
# it was meant to fix. The chamber is only 4.7 port diameters long, far shorter
# than the 10-20 diameters swirl needs to decay, so whatever is imparted
# persists the whole length. report() prints S and warns past 0.6.
RAD_N       = 12         # vanes -- see (1) above
RAD_HUB_R   = 0.006      # central hub radius (Oe 12 mm)
RAD_C_AXIAL = 0.008      # AXIAL extent of the vane, held fixed across alpha so
#                          the screen does not confound swirl with solidity
RAD_T       = 0.0010     # vane thickness


def swirl_number(alpha_deg, hub_r=RAD_HUB_R, tip_r=DIFF_RI):
    h = hub_r / tip_r
    return (2.0 / 3.0) * math.tan(math.radians(alpha_deg)) \
        * (1 - h ** 3) / (1 - h ** 2)


def _rad_point(r, theta, y):
    return (PORT_X + r * math.cos(theta), y, PORT_Z + r * math.sin(theta))


def _rad_camber(s, alpha, r_mean):
    """(axial y offset, azimuthal offset) at fractional chord s.

    Same circular-arc construction as camber(), turning in the (axial,
    tangential) plane instead of the (axial, vertical) one, and scaled so the
    AXIAL projection is RAD_C_AXIAL at every alpha.
    """
    if alpha < 1e-9:
        return RAD_C_AXIAL * s, 0.0
    L = RAD_C_AXIAL * alpha / math.sin(alpha)
    phi = alpha * s
    return (L * math.sin(phi) / alpha,
            L * (1.0 - math.cos(phi)) / alpha / r_mean)


def write_radial_vane(f, theta0, alpha, ns=14, nu=18):
    """One closed swirl vane, hub to shroud. Normals point out of the solid.

    The surface normal is taken from finite differences of the camber surface
    rather than analytically: the vane is a twisted ruled surface (the azimuthal
    offset is a fixed ANGLE, so the tangential displacement grows with radius),
    and differencing the actual grid cannot disagree with the geometry it is
    offsetting the way a hand-derived normal can.
    """
    r0, r1 = RAD_HUB_R - VANE_LAP, DIFF_RI + VANE_LAP
    r_mean = (RAD_HUB_R + DIFF_RI) / 2

    mid = []
    for i in range(ns + 1):
        dy, dth = _rad_camber(i / ns, alpha, r_mean)
        mid.append([_rad_point(r0 + (r1 - r0) * j / nu, theta0 + dth,
                               VANE_Y0 + dy) for j in range(nu + 1)])

    up, lo = [], []
    for i in range(ns + 1):
        rowu, rowl = [], []
        for j in range(nu + 1):
            a = mid[min(i + 1, ns)][j]
            b = mid[max(i - 1, 0)][j]
            c = mid[i][min(j + 1, nu)]
            d = mid[i][max(j - 1, 0)]
            u = (a[0] - b[0], a[1] - b[1], a[2] - b[2])   # along chord (i)
            v = (c[0] - d[0], c[1] - d[1], c[2] - d[2])   # along span  (j)
            # v x u, NOT u x v. write_thick_body winds its top face so that the
            # face normal comes out as -(d_i x d_j), so `up` must be offset in
            # that same direction or the whole body is inside out -- which is
            # still CLOSED and ORIENTED, and shows up only as a negative signed
            # volume. Same trap as the shroud, one level further in.
            n = (v[1] * u[2] - v[2] * u[1],
                 v[2] * u[0] - v[0] * u[2],
                 v[0] * u[1] - v[1] * u[0])
            m = math.sqrt(sum(t * t for t in n)) or 1.0
            n = tuple(t / m * RAD_T / 2 for t in n)
            p = mid[i][j]
            rowu.append((p[0] + n[0], p[1] + n[1], p[2] + n[2]))
            rowl.append((p[0] - n[0], p[1] - n[1], p[2] - n[2]))
        up.append(rowu)
        lo.append(rowl)
    return write_thick_body(f, up, lo)


def write_hub(f, nseg):
    """Closed cylinder the vanes are rooted in. Ends overhang by VANE_LAP so the
    vane leading/trailing edges are buried rather than flush with the hub caps."""
    y0 = VANE_Y0 - VANE_LAP
    y1 = VANE_Y0 + RAD_C_AXIAL + VANE_LAP
    nf = 0
    for i in range(nseg):
        a0, a1 = TWO_PI * i / nseg, TWO_PI * (i + 1) / nseg
        p00, p10 = _rad_point(RAD_HUB_R, a0, y0), _rad_point(RAD_HUB_R, a1, y0)
        p01, p11 = _rad_point(RAD_HUB_R, a0, y1), _rad_point(RAD_HUB_R, a1, y1)
        c0, c1 = (PORT_X, y0, PORT_Z), (PORT_X, y1, PORT_Z)
        # Reversed from the obvious ordering: p00 -> p10 -> p11 winds so the
        # normal comes out as -e_r, i.e. into the hub. Outward is +e_r.
        nf += quad(f, p01, p11, p10, p00)      # side, normal radially outward
        nf += facet(f, c0, p00, p10)           # upstream cap, normal -y
        nf += facet(f, c1, p11, p01)           # downstream cap, normal +y
    return nf


def write_shroud(f, nseg):
    """The Oe41/Oe44 x 10 mm ring both diffuser types are built in."""
    y0, y1 = -DIFF_EMBED, DIFF_L
    nf = 0
    for i in range(nseg):
        a0, a1 = TWO_PI * i / nseg, TWO_PI * (i + 1) / nseg
        oi0, oi1 = _rad_point(DIFF_RI, a0, y0), _rad_point(DIFF_RI, a1, y0)
        oj0, oj1 = _rad_point(DIFF_RI, a0, y1), _rad_point(DIFF_RI, a1, y1)
        qi0, qi1 = _rad_point(DIFF_RO, a0, y0), _rad_point(DIFF_RO, a1, y0)
        qj0, qj1 = _rad_point(DIFF_RO, a0, y1), _rad_point(DIFF_RO, a1, y1)
        # Normals point OUT of the shell, i.e. into the fluid -- on the INNER
        # wall that means radially INWARD, towards the bore. Getting this
        # backwards is invisible to the closure test (a consistently inverted
        # body is still closed and oriented) and shows up only as a negative
        # signed volume, which is what caught it the first time.
        nf += quad(f, oi1, oj1, oj0, oi0)      # inner wall
        nf += quad(f, qj0, qj1, qi1, qi0)      # outer wall
        nf += quad(f, qi0, qi1, oi1, oi0)      # upstream rim (buried)
        nf += quad(f, oj1, qj1, qj0, oj0)      # downstream rim
    return nf


def write_radial_diffuser(path, alpha_deg, n_vanes):
    alpha = math.radians(alpha_deg)
    nseg = port_segments(DIFF_RO)
    with open(path, "w") as f:
        f.write("solid diffuser\n")
        nf = write_shroud(f, nseg)
        nf += write_hub(f, max(32, nseg // 4))
        for k in range(n_vanes):
            nf += write_radial_vane(f, TWO_PI * k / n_vanes, alpha)
        f.write("endsolid diffuser\n")
    return nf


def radial_volumes(alpha_deg, n_vanes, ns=14):
    """(signed-sum volume, fluid displaced), same split as diffuser_volumes."""
    alpha = math.radians(alpha_deg)
    ring = math.pi * (DIFF_RO ** 2 - DIFF_RI ** 2)
    shroud_sum, shroud_disp = ring * (DIFF_L + DIFF_EMBED), ring * DIFF_L

    hub_len = RAD_C_AXIAL + 2 * VANE_LAP
    hub = math.pi * RAD_HUB_R ** 2 * hub_len

    span = (DIFF_RI + VANE_LAP) - (RAD_HUB_R - VANE_LAP)
    r_mean = (RAD_HUB_R + DIFF_RI) / 2
    arc = RAD_C_AXIAL if alpha < 1e-9 else RAD_C_AXIAL * alpha / math.sin(alpha)
    vanes = n_vanes * span * arc * RAD_T
    # each vane is buried VANE_LAP into the hub and VANE_LAP into the shroud
    lap = n_vanes * 2 * VANE_LAP * arc * RAD_T
    return shroud_sum + hub + vanes, shroud_disp + hub + vanes - lap


def write_diffuser(path, tilt_deg, n_vanes):
    """Shroud + n_vanes as separate closed bodies in one multi-solid STL.

    They overlap slightly by design (VANE_LAP), which is fine for snappy and for
    verify_closed -- disjoint OR overlapping closed surfaces both satisfy
    'every edge shared by exactly two facets'. The signed volume then
    double-counts the overlaps, so diffuser_volumes() reports that sum for the
    verification and the UNION separately for the V_air bookkeeping.
    """
    tilt = math.radians(tilt_deg)
    nseg = port_segments(DIFF_RO)
    with open(path, "w") as f:
        f.write("solid diffuser\n")
        nf = write_shroud(f, nseg)
        for z0 in vane_z_positions(n_vanes):
            nf += write_vane(f, z0, tilt)
        f.write("endsolid diffuser\n")
    return nf


def diffuser_volumes(tilt_deg, n_vanes, ns=16):
    """(signed-sum volume, fluid displaced) for the diffuser.

    The two differ for two independent reasons and conflating them is how a
    deliberate overlap silently becomes a geometry error:
      * the vane ends overlap the shroud shell (counted twice in the sum);
      * the part of the shroud upstream of y = 0 is OUTSIDE the fluid domain, so
        it displaces nothing.
    """
    tilt = math.radians(tilt_deg)
    ring = math.pi * (DIFF_RO ** 2 - DIFF_RI ** 2)
    shroud_sum = ring * (DIFF_L + DIFF_EMBED)
    shroud_disp = ring * DIFF_L

    vane_sum = lap = 0.0
    for z0 in vane_z_positions(n_vanes):
        for i in range(ns):
            s0, s1 = i / ns, (i + 1) / ns
            y0, zz0, _, _ = camber(s0, tilt, z0)
            y1, zz1, _, _ = camber(s1, tilt, z0)
            ds = math.hypot(y1 - y0, zz1 - zz0)
            hw = (vane_halfwidth(zz0) + vane_halfwidth(zz1)) / 2
            vane_sum += 2.0 * hw * VANE_T * ds
            lap += 2.0 * VANE_LAP * VANE_T * ds     # both ends, inside the shell
    return shroud_sum + vane_sum, shroud_disp + vane_sum - lap


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

    # .get, NOT half[...] -- `half` is a defaultdict, so indexing a missing
    # reversed edge INSERTS it and raises "dictionary changed size during
    # iteration". That only ever fires on a surface which is actually open,
    # i.e. exactly when this check is supposed to report something useful.
    unmatched = [e for e in half if half.get((e[1], e[0]), 0) != half[e]]
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


def report(profile, diff_disp=0.0, tilt_deg=None, n_vanes=0):
    area = arc = 0.0
    for i in range(len(profile) - 1):
        dx = profile[i + 1][0] - profile[i][0]
        area += dx * ((profile[i][1] - BOX_H) + (profile[i + 1][1] - BOX_H)) / 2
        arc += math.hypot(dx, profile[i + 1][1] - profile[i][1])
    hood_v = area * DEPTH
    box_v = WIDTH * BOX_H * DEPTH
    shell_v = box_v + hood_v            # what chamber.stl encloses (no tray)
    # DISPLACED, not the STL volume -- the tray is written 1 mm oversize, and
    # that margin lies inside the wall material where there is no fluid to remove.
    v_air = shell_v - TRAY_DISP_V - diff_disp
    print("  hood apex            %8.4f cm   (expect 14.3334)" % (max(p[1] for p in profile) * 100))
    print("  internal lip height  %8.4f cm   (expect  0.394)" % ((profile[0][1] - BOX_H) * 100))
    print("  hood x-section       %8.4f cm2  (expect 38.80)" % (area * 1e4))
    print("  hood arc length      %8.4f cm   (expect 15.28)" % (arc * 100))
    print("  tray footprint       %8.4f cm2  (expect 224.00, = full floor)"
          % (WIDTH * DEPTH * 1e4))
    print("  tray displaced       %8.4f L    (expect  0.560)" % (TRAY_DISP_V * 1e3))
    print("  port diameter        %8.4f mm   (Oe 40 default since 2026-08-16)"
          % (2e3 * PORT_R))
    print("  port area            %8.4e m2" % (math.pi * PORT_R ** 2))
    print("  port z span          %8.4f .. %.4f cm  (tray top 2.50, spring 9.67)"
          % ((PORT_Z - PORT_R) * 100, (PORT_Z + PORT_R) * 100))
    if tilt_deg is not None:
        print("  diffuser             %d vanes at %.0f deg, displaces %.4f L"
              % (n_vanes, tilt_deg, diff_disp * 1e3))
    print("  V_air                %8.4f L    (no diffuser: 2.330)" % (v_air * 1e3))
    # v_air is in m3. ACH = Q / V_air with Q in m3/h; tau = V_air / Q in seconds.
    for q in (11.77, 1.25):
        print("  ACH @ %5.2f m3/h     %8.0f h-1  tau %.2f s" %
              (q, q / v_air, 3600.0 * v_air / q))

    # Written so generate_case.sh does not have to keep its OWN copy of V_air.
    # A duplicated constant is exactly what drifted when the tray went flush --
    # V_air moved 2.530 -> 2.3296 L and every script carrying it had to be found
    # by hand. The diffuser moves it again, per tilt.
    return shell_v, TRAY_STL_V, v_air


def main():
    global PORT_R
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--profile-points", type=int, default=200)
    ap.add_argument("--port-r", type=float, default=PORT_R,
                    help="port radius in metres (default %(default)s = Oe 40 mm)")
    ap.add_argument("--diffuser-tilt", type=float, default=None,
                    help="inlet vane angle in degrees -- downward tilt for "
                         "type=cascade, swirl cant for type=radial. Omit for "
                         "no diffuser (the control case)")
    ap.add_argument("--diffuser-type", choices=("cascade", "radial"),
                    default="cascade")
    ap.add_argument("--diffuser-vanes", type=int, default=None,
                    help="default 5 for cascade, %d for radial" % RAD_N)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    PORT_R = args.port_r
    if PORT_Z + PORT_R > BOX_H:
        raise SystemExit("port r=%.4f breaks out of the box section: top edge "
                         "z=%.4f > %.4f" % (PORT_R, PORT_Z + PORT_R, BOX_H))
    if PORT_Z - PORT_R < TRAY_H:
        raise SystemExit("port r=%.4f reaches below the tray top" % PORT_R)
    if args.diffuser_tilt is not None and DIFF_RO > PORT_R + WALL:
        print("  !! diffuser shroud (r=%.4f) is wider than the port + wall "
              "(%.4f) -- its rim will not be buried in solid" %
              (DIFF_RO, PORT_R + WALL))

    out = os.path.join(args.case, "constant", "triSurface")
    os.makedirs(out, exist_ok=True)

    profile = hood_profile(args.profile_points)
    chamber = os.path.join(out, "chamber.stl")
    tray = os.path.join(out, "tray.stl")
    write_chamber(chamber, profile)
    write_tray(tray)

    nv = args.diffuser_vanes
    if nv is None:
        nv = RAD_N if args.diffuser_type == "radial" else 5

    diffuser = os.path.join(out, "diffuser.stl")
    diff_sum = diff_disp = 0.0
    if args.diffuser_tilt is None:
        if os.path.exists(diffuser):
            os.remove(diffuser)        # control case: leave no stale surface
    elif args.diffuser_type == "radial":
        write_radial_diffuser(diffuser, args.diffuser_tilt, nv)
        diff_sum, diff_disp = radial_volumes(args.diffuser_tilt, nv)
        S = swirl_number(args.diffuser_tilt)
        print("  radial diffuser      %d vanes at %.0f deg, swirl number S = %.2f"
              % (nv, args.diffuser_tilt, S))
        if S > 0.6:
            print("  !! S = %.2f EXCEEDS 0.6 -- expect vortex breakdown and a"
                  % S)
            print("     central recirculation bubble. In an open room that is the"
                  " mixing")
            print("     mechanism; in a closed 2.3 L box it is re-breathing.")
    else:
        write_diffuser(diffuser, args.diffuser_tilt, nv)
        diff_sum, diff_disp = diffuser_volumes(args.diffuser_tilt, nv)

    print("wrote %s (%d profile points)" % (out, args.profile_points))
    shell_v, tray_v, v_air = report(profile, diff_disp, args.diffuser_tilt, nv)

    # Single source of truth for the derived quantities generate_case.sh needs.
    with open(os.path.join(out, "geometry.info"), "w") as f:
        on = args.diffuser_tilt is not None
        f.write("PORT_R %.9e\nPORT_AREA %.9e\nV_AIR %.9e\n"
                "DIFF_TYPE %s\nDIFF_TILT %s\nDIFF_VANES %d\nDIFF_DISP %.9e\n"
                "DIFF_SWIRL %s\n"
                % (PORT_R, math.pi * PORT_R ** 2, v_air,
                   args.diffuser_type if on else "none",
                   "%.3f" % args.diffuser_tilt if on else "none",
                   nv if on else 0,
                   diff_disp,
                   "%.4f" % swirl_number(args.diffuser_tilt)
                   if on and args.diffuser_type == "radial" else "none"))

    if args.verify:
        ok = verify_closed(chamber, shell_v) & verify_closed(tray, tray_v)
        if args.diffuser_tilt is not None:
            ok &= verify_closed(diffuser, diff_sum)
        if not ok:
            raise SystemExit("surface failed verification -- do not mesh with this")


if __name__ == "__main__":
    main()
