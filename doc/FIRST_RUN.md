# First run — what to check, in order

**Nothing in `templates/` or `scripts/` has ever been executed.** It was authored on the
Windows box, which has no OpenFOAM, no usable WSL distro and no Python (CLAUDE.md §2.1). Treat
every file as unverified until it runs. This page lists the failure points in the order they
will bite, most likely first.

```bash
. /usr/bin/openfoam2606
cd ~/OpenFOAM/henry-v2606/run/microgreenChamber
chmod +x scripts/*.sh templates/Allrun templates/Allclean

# smallest possible smoke test first — m1, serial, minutes not hours
scripts/generate_case.sh --name p1_smoke_m1 --mesh m1
cd runs/p1_smoke_m1 && ./Allrun
```

---

## 1. `make_geometry.py` — highest risk

Never run, never even syntax-checked. Everything downstream depends on it.

```bash
python3 scripts/make_geometry.py --case /tmp/geomtest --verify
```

`--verify` checks every edge is shared by exactly two facets and refuses to emit a leaky
surface. It also prints the derived geometry against expected values:

| | Expected |
|---|---|
| hood apex | 14.3334 cm |
| internal lip height | 0.394 cm |
| hood cross-section | 38.80 cm² |
| hood arc length | 15.28 cm |
| `V_air` | 2.530 L |

If those match and the surfaces report `CLOSED`, the geometry is right. Look at
`constant/triSurface/chamber.stl` in ParaView regardless — a surface can be closed and still
be wrong.

The delicate part is `write_end_wall()`: a convex polygon with a circular hole, triangulated
by ray-casting from the port centre and merging with the polygon's own vertices. It is closed
by construction *if* the cross-section really is convex (it is — a rectangle capped by a
concave curve) and the port centre really is inside it. `_ray_hit` raises rather than
producing garbage if that assumption breaks.

## 2. Patch names after snappy — most likely dict error

`0.orig/*`, `snappyHexMeshDict`'s `layers`, and every function object assume the patches come
out named exactly:

```
floor  walls  hood  inlet  outlet  tray
```

snappy sometimes names region patches `<surface>_<region>` — i.e. `chamber_floor`, `tray_tray`
— depending on how the geometry `regions` block is written. **Check first:**

```bash
foamDictionary constant/polyMesh/boundary -keywords
```

If they are prefixed, either fix the `name` entries in `snappyHexMeshDict`'s `geometry` block
(preferred — one place) or update the BC regexes. Do not do both.

## 3. `background` patch must have zero faces

If `constant/polyMesh/boundary` still lists `background` with a non-zero face count, the STL
is not closed or `locationInMesh (0.0613 0.0917 0.0613)` landed in the wrong region. Fix the
geometry — do not delete the patch.

## 4. `checkMesh`

`Allrun` stops if `checkMesh` prints `***`. Expect trouble at:

- **the hood/lip junction** — a 55° corner with layers on both sides;
- **the tray side slots** — 2.5 mm wide, level-2 refined to ~6 cells, no layers by design.

Non-orthogonality < 65 and skewness < 4 (CLAUDE.md §9.1). Then set
`nNonOrthogonalCorrectors` in `fvSolution` to match what you actually got, rather than leaving
it at 1.

## 5. Function objects

`sampledSurface` with `bounds` (used by `trayPlane` and `traySlotFlux`) is the syntax most
likely to need adjusting for v2606. If a function object fails, the solver keeps going and you
lose the metric silently — check `log.simpleFoam` for FO warnings on the first run, not the
tenth.

`age` needs `phi`; `trayMinMax` needs the `canopyZone` cellZone from `topoSet`.

## 6. First real result

Only once m1 completes end to end:

```bash
scripts/sweep_Q.sh          # 5 / 2.5 / 1.25 m³/h at m2 — the Phase 1 study
```

Then walk CLAUDE.md §9 before calling any of it a result. In particular §9.4 — inlet flux plus
outlet flux ≈ 0 — catches bad BC pairings faster than anything else.

---

## Known-unverified list

| Item | Risk |
|---|---|
| `make_geometry.py` | never executed |
| snappy patch naming | assumption, see §2 above |
| `sampledSurface` `bounds` syntax | v2606 form unconfirmed |
| `externalWallHeatFluxTemperature` `mode power` on `hood` | Phase 2 only, untested |
| Cell counts (0.2 M / 1.3 M / 9 M after snapping) | estimates, not measured |
| `expansionRatio`/`finalLayerThickness` layer settings | copied conventions, not tuned |
