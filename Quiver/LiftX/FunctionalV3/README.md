# LIFT X LH / AXIS 340 — functional quiver prototype V3

**Use this revision for fit testing. Do not print MountV2: its closed shaft ports trap complete arrows. This revision is not yet approved for shooting or a 10,000-unit production run.**

[Open the editable assembly in CAD Viewer](http://127.0.0.1:3245/C:/Users/metzd/Documents/GitHub/FreeCAD/Quiver/LiftX/FunctionalV3?file=LiftX_LH_Assembly.step.py). The adjacent STEP opens in FreeCAD and other CAD software. `STL/` and `3MF/` contain individually oriented manufacturing parts. **3MF files are geometry-only, not sliced Bambu projects. Never print the assembly, foam, hardware, or loaded reference as one object.**

## What is now functional in the geometry

- Five staggered arrow positions, 44 mm nearest-neighbor pitch.
- Enclosed broadhead hood with a genuinely open mouth **facing down toward the shaft grippers**. There is no floor or hard shaft hole to thread an arrow through.
- Spine is directly fused along the hood's back wall, with a continuous cap-down print transition. No separate diagonal attachment struts.
- One replaceable TPU gripper, with side-entry mouths and open-front rigid saddles. The hard carrier leaves a checked 9.3 mm-radius front-half space around each jaw so it can flex; actual release force remains untested.
- Two frame pieces, a 34 mm overlap tongue/socket, 0.30 mm nominal clearance per socket side, and two transverse M4 fasteners. Assembly is approximately 360 mm tall; each printed part fits the A1.
- A slide-off dock with an exposed release and screw flange. A continuous shallow channel behind the lower spine clears the fixed latch base during removal. **Its bow interface is provisional, not a dimensional copy of Mathews LowPro.**

## Choose the AXIS gripper first

**The user confirmed AXIS 340. Print `gripper_axis_340`, not the other variants.** Its listed outside diameter is 6.7818 mm; the initial TPU bore is 6.5318 mm. Begin with the four-dot sample on the coupon. Easton '5 mm' is not a literal 5 mm outside diameter. Check the actual shaft with calipers and trial the printed fit. Each variant file contains one complete five-position insert; the other sizes are optional alternatives, not additional assembly pieces.

| AXIS spine / filename suffix | Manufacturer OD, mm | Coupon dot count |
|---|---:|---:|
| 600 | 6.4262 | 1 |
| 500 | 6.5532 | 2 |
| 400 | 6.7056 | 3 |
| 340 | 6.7818 | 4 |
| 300 | 6.9850 | 5 |
| 260 | 7.1120 | 6 |
| 200 | 7.2644 | 7 |

Source: [Easton's AXIS specification table](https://eastonarchery.com/arrows_/5mm-axis-carbon-arrows/). These variants are for the listed standard AXIS series, not an assertion about every AXIS-branded product.

Print `axis_sizing_coupon` in the same TPU as the final insert. Coupon bores have 0.25 mm diametral interference and side throats 65% of nominal shaft OD. Check grip and sideways release on a bare shaft. A material/tolerance trial is required; do not compensate for a poor fit by forcing or scraping a carbon shaft. The seven samples are identified by one through seven recessed dots.

## Broadhead limits and loading

Design storage envelope per head: **35 mm diameter × 70 mm axial length**, including ferrule and blades. For a mechanical head, measure the *closed/stored* geometry, not its deployed cutting diameter. This is a bounded compatibility target, not 'all standard broadheads.' For context, [G5 lists Montec cutting widths of 1–1 1/8 in](https://shop.g5outdoors.com/products/montec); length, orientation, actual stored shape, foam engagement and containment still need checking.

A 12 mm cut-foam template is shown inside the cap. Use appropriate replacement quiver foam and a compatible adhesive; the model is not a printed insert. Blade retention, foam durability and protection against puncture have not been tested. Start with blunt dummy envelopes or field points, not exposed sharp broadheads.

To remove an arrow: release the shaft sideways from its TPU mouth while the tip remains in the hood; withdraw along the slightly tilted shaft until the head clears the mouth; then move outboard. Reverse to load. The checked path uses about 2.33° of pivot, 95 mm withdrawal, then 100 mm outward travel. It is sampled geometry, not a required exact hand motion or an ergonomic test.

## Printed parts and assembly

| Component | Quantity | Print orientation | Bounding box, mm |
|---|---:|---|---:|
| Lower spine/carrier | 1 | Carrier on bed | 108 × 93.4 × 228 |
| Hood/upper spine | 1 | Closed cap on bed | 144 × 102.1 × 166 |
| Provisional dock | 1 | Bow-contact face on bed | 57 × 80 × 24.6 |
| Selected TPU gripper | 1 | Flat upper face on bed, pegs last | about 104 × 53.8 × 12.7 |

Additional BOM: two metal M4×16 screws with approximately 7 mm heads, two M4 hex nuts (check actual head/nut dimensions), one cut foam insert, compatible adhesive, and two bow mounting screws/washers **selected only after the actual interface is verified**. Hardware in the STEP is simplified reference geometry, not a printable substitute.

Seat the TPU insert in the carrier and pull its two soft mushroom pegs into the recessed anchor holes. Slide the upper socket over the lower tongue to the shoulder; insert the nuts and M4 screws. Do not crush the printed walls or invent a torque specification. Bond foam in the cap. Test the quiver off the bow before considering installation.

## A1 print starting point — not a validated slicer profile

For rigid parts, begin with dried PETG, 0.4 mm nozzle, 0.20 mm layers, 5 walls, 6 top/bottom layers and 35% infill. Use an 8–10 mm brim on the tall lower frame and conservative acceleration. TPU 95A: start with 0.20 mm layers, 4 walls and solid infill, using the filament maker's temperature/speed range. Confirm nozzle/filament compatibility.

The hood's cap-down orientation avoids supporting its entire cavity. Local horizontal bolt/nut holes, the lower frame's approximately 16.4 mm latch-window roof, and especially the dock's long release tongue still require layer-preview/bridge assessment and removable local support where needed. Clean the rail and latch completely after support removal. **This is not a support-free design.** Upright frame printing puts bending stresses across layer bonds; stiffness, strength, creep and fatigue require printed-part tests.

Mesh checks identify downward faces steeper than 45° and verify build-volume fit. Bambu Studio's installed Windows launcher returned no CLI output; no successful Bambu slice, print time, mass, strength, or production throughput is claimed. Inspect every layer in Bambu Studio before printing.

## Mounting on this bow is still a release gate

The user setup is left-handed LIFT X, a Spot-Hogg through-riser/dovetail sight of unconfirmed model, and QAD MX2 UltraRest. No measured mounting-side geometry is available.

The flange has a generic 33.325 mm accessory-hole pitch, 5.30 mm clearance and a 3 mm-travel lower slot. That does **not** establish available holes, correct threads, flat seating or cable/rest/sight clearance on this bow. The old MountV2 pattern gauge may be used only as a non-load-bearing comparison tool; its quiver chassis remains rejected. Do not drill the bow, alter Bridge-Lock/rest clamps, force screws, or guess OEM LowPro dimensions. [Mathews' own LowPro compatibility statement](https://mathewsinc.com/products/lowpro-detachable-quiver) is not certification of this custom mount.

Before making a usable bow mount, obtain a mounting-side photo and measured interface or an appropriate manufacturer-compatible adapter. Then check tool access, screw engagement, all adjustments, quiver slide travel and full draw-cycle clearance with an archery technician. No shooting with this unvalidated mount.

## Evidence and production gates

`Review/functional_validation.json`: five complete-arrow paths, **85 samples per arrow**, using 35×70 mm cylindrical head envelopes and 7.2644 mm shafts with the other four arrows stationary. Zero hard-part/neighbor overlap in the checked samples. Foam/TPU contact is intentionally excluded. Also checks the joint, TPU fit/expansion space and 43 dock-slide positions.

`Review/harness_validation.json`: per-part topology, closed-solid and self-intersection checks. `mesh_validation.json`: STL/3MF watertightness, winding, bounds, overhang-area indicators and artifact hashes. `freecad_roundtrip.json` checks the exported STEP files independently in FreeCAD 1.1. Snapshot result JSONs identify reviewed multi-view CAD images; `REFERENCE_hood_section_DO_NOT_PRINT` is a cutaway of live geometry, never a manufacturing part. `CAD_BRIEF.md` records assumptions and unresolved requirements.

Four printed component types reduce assembly, but this is **not production-qualified**. Before 10,000 units: prove material/shaft retention across tolerance lots, broadhead containment and separation, joint strength, latch retention/fatigue, vibration, impact, temperature/UV/moisture and draw-cycle clearance. Then establish actual sliced mass/cycle time, assembly labor and go/no-go gauges from a pilot run. Previous topology/FEA claims do not apply to this rebuilt geometry.

Canonical build: `python build_delivery.py`; functional check: `python validate_function.py`. Requires build123d 0.11.1, trimesh and the installed text-to-CAD harness. All STEP sources derive live geometry from `quiver_common.py`; none re-import their own exported STEP.
