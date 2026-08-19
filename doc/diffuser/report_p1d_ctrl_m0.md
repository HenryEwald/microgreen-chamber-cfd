# p1d_ctrl_m0 — control, no diffuser

**The reference arm.** Ø 40 mm plain circular cutouts, flush with the end walls, no vanes.
Everything else in the screen is measured against this.

| | |
|---|---|
| solver / model | `pimpleFoam`, kOmegaSST, isothermal |
| mesh | m0, **382,613** cells, `checkMesh` OK |
| `Q` | 11.77 m³/h (3.26861e-3 m³/s), `Re_port` = 6863 — turbulent |
| τ | 0.7127 s · endTime 4.69 s = 6.6 τ |
| Δt | 8.333e-4 s, bound by `maxDeltaT` (jet Courant 2.6) |
| wall clock | **2.77 h**, 5,647 steps, 8 ranks on CCD0 |
| frames kept | **5** ⚠ |

## Result

| metric | value | vs target |
|---|---|---|
| tray mean \|U\| | **0.3040 ± 0.0041 m/s** (RMS 3.7 %) | bottom edge of the 0.3–0.8 band |
| tray CoV | 0.665 | |
| ventilation ε_a | **20.1 %** | perfect mixing 50 %, piston 100 % |
| mean age | 2.49 τ | |
| hood age | 2.67 τ (1.07× the mean) | |
| worst cell | 5.29 τ | |
| domain max \|U\| | 3.41 m/s = 1.31 × `U_in` | jet core survives |

**The chamber is a jet plus a slow recirculation, and it is stale.** ε_a = 20 % means the air
is on average 2.5 flow-throughs old — half the effectiveness of a perfectly mixed box. The tray
sits at the very bottom of the target band, so the crop is at the edge of "not enough air"
before any plant resistance is added.

The domain maximum is only 1.31 × the port bulk velocity, against 2.1–2.7× for every diffused
arm — the plain port is the only case that does not accelerate the flow anywhere, because
there is no blockage to squeeze it through.

## Acceptance (CLAUDE.md §9)

| # | check | result |
|---|---|---|
| 1 | `checkMesh` | Mesh OK |
| 3 | continuity | small, not growing |
| 4 | **mass balance** | inlet −3.26861e-03, outlet +3.26861e-03 → **0.0e+00** ✓ |
| 5 | monitored quantities | tray signal stationary, RMS 3.7 % over the last 2 τ |
| 6 | mesh independence | ⚠ **not established at this operating point** |
| 7 | steady assumption | n/a — transient by design |
| — | **age identity** `<age>_outlet/τ` | **0.99951 (−0.049 %)** ✓ certified |
| — | y⁺ | area-avg **1.07**, max 5.51 — viscous sublayer, the best of the four |

## ⚠ Only 5 frames

This case ran before the 2026-08-16 `purgeWrite 0` change and kept `purgeWrite 5` with
`writeInterval 0.5`. It therefore holds **5 time directories at 0.5 s spacing (t = 2.5 … 4.5)**
where every other case holds 60 at 0.08 s.

Consequences:
- **Time-averaged quantities are unaffected** — `fieldAverage` ran every step from t = 1.95 s,
  so `UMean`/`phiMean`, the age field, and every `postProcessing` time series are complete and
  valid. Everything in the table above stands.
- **The animation is 5 frames** and cannot show unsteadiness. `anim_p1d_ctrl_m0_x/animation.gif`
  is a 5-frame strip, not a comparable movie.
- The history cannot be recovered — `purgeWrite` deletes as the run proceeds. Re-running is
  ~2.8 h.

## What the pictures show

`vent_p1d_ctrl_m0/02_slice_x.png` is the clearest single image in the screen: **a narrow fresh
jet running straight from the inlet to the outlet, with everything above and below it stale.**
The jet core is near-black (age → 0) and barely spreads over the 187 mm path; the hood above it
and the tray region below it both sit at 2.2–2.6 s, i.e. **3–3.6 τ**.

That is **short-circuiting** in its textbook form — supply air reaching the exhaust without
having mixed with the room — and it is the mechanistic explanation for ε_a = 20 %. The chamber
is not badly ventilated because the fan is too weak; it is badly ventilated because most of the
delivered air never touches most of the volume.

**It also explains why the tray metric is only 0.30 m/s while the domain maximum is 3.41 m/s.**
The momentum is all in a jet that passes 32 mm above the crop.

## Files

- `anim_p1d_ctrl_m0_x/` — mid-width slice (jet, hood, tray) ⚠ 5 frames
- `anim_p1d_ctrl_m0_x_log/`, `anim_p1d_ctrl_m0_z_log/` — same views, **log scale 0.007–7 m/s**, for flow structure where the linear set saturates
- `anim_p1d_ctrl_m0_z/` — port-centreline plan view ⚠ 5 frames
- `vent_p1d_ctrl_m0/` — 3D ventilation maps, scale 0 → 3.0 s shared with all cases
- `mesh_ctrl/` — mesh inspection renders
