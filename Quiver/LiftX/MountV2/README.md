# LIFT X quiver — left-hand mounting revision

**REJECTED — DO NOT PRINT THIS QUIVER.** The upward-opening basket and closed shaft ports prevent normal loading/removal of complete broadheaded/fletched arrows. Earlier geometric checks below did not establish function. Use [FunctionalV3](../FunctionalV3/README.md) for the corrected loading-path prototype; its bow mount still requires measured fit verification. Everything below is historical, not a current recommendation.

September 8, 2026. **Fit-check prototype, not a production-qualified bow accessory.** Use this folder instead of the earlier LiftX print pack.

Configured for the user's left-hand Mathews LIFT X, Spot-Hogg Eddie sight described as Bridge-Lock-style, and QAD MX2 UltraRest. The exact sight variant, riser attachment geometry, and installed quiver blocks have not been measured. This model does **not** copy or fit the proprietary LowPro receiver.

## What changed

- Two printed production parts remain: one basket/spine/clip chassis and one slide-on dock with integral release tongue.
- Fixed the handedness code: the geometry actually mirrors, not just its label.
- Rebuilt the basket with aligned inner/outer taper stations. Its open top has a continuous rim; the sides have no decorative holes. Five intentional shaft ports remain in the floor.
- Both spine chords blend directly into the basket wall/floor. No separate angled connector tabs.
- Broader faceted corners improve the main basket flare's worst print angle to approximately 45.9 degrees above horizontal, without increasing height. Local ledges and bridges still need slicer review/support.
- Moved both mounting screws onto an exposed integral flange, away from the moving latch. Upper round hole locates the dock; the lower short slot accommodates small pitch variation.
- The dock exports back-face-down so the long latch axis lies in the print plane. Remove local support beneath the flexure before testing it.
- Assembly STEP retains two separately named parts. The optional mounting-pattern gauge is a test tool, not a third production component.

## Mounting: check first, then print

1. Print `STL/mount_pattern_gauge.stl` flat. It is 32 × 60 × 2 mm, about 3.6 cm³ of plastic. Do not use it as a structural mount or spacer.
2. With the bow unloaded, compare it to the **available accessory/sight mounting holes**, not the rest clamp or Bridge-Lock bore. Nominal pattern: 33.325 mm vertical centers; 5.30 mm clearance; lower slot has 3 mm total extra travel. Confirm the threads are 10-24 UNC before introducing screws. Do not force a mismatched thread.
3. If the holes are occupied, absent, or the flange does not seat flat, stop. This revision needs the actual mounting-side photo/dimensions or an appropriate manufacturer-compatible adapter. Do not drill the bow, alter the sight/rest clamps, or substitute guessed LowPro dimensions.
4. After the pattern and surrounding space check out, print the dock. Fit it with **two appropriate metal screws and flat washers**. The flange is 6 mm thick; select screw length from actual mounting depth, washer thickness, thread engagement and bottoming clearance. No universal bolt length or torque is specified. Use the bow/accessory manufacturer's limits or an archery technician.
5. The flange gives access to both screw heads while the chassis is installed. Install the dock once; align the quiver's male rail above the open track and slide down to its stop. Confirm that the tongue engages the notch, then perform an unloaded retention check. Press the release away from the bow and lift the chassis approximately 84 mm to clear it. A small unmeasured gap around the bow or sight is not a clearance approval.
6. Check the complete sight adjustment range, rest movement, cables/string path and quiver installation/removal path on the actual bow. Have an archery technician verify clearance through the draw cycle before shooting. Do not load broadheads until containment and retention are proven.

The standard accessory pattern is documented in the [ATA technical guide, ATA/BOW-108-2008, page 30](https://www.sksabac.eu.org/download/ATATECHGUIDE_FIN.pdf); it is not a LowPro interface drawing or evidence of available holes on this particular setup. Mathews lists LIFT X compatibility for its own [LowPro Detachable](https://mathewsinc.com/products/lowpro-detachable-quiver), designed around Bridge-Lock and the Integrate MX2. Those facts do not certify this custom mount.

## Bambu Lab A1 starting setup

| Print | Exported print envelope, mm | Orientation |
|---|---:|---|
| Chassis | 126 × 66.7 × 248 | Upright, lower clip carrier on bed |
| Dock | 57 × 80 × 24.6 | Broad bow-contact face on bed |
| Optional gauge | 32 × 60 × 2 | Flat |

The chassis has 8 mm nominal height margin within the user's 256 mm cube. Add a 10–12 mm brim and center it on the plate. Start with dried PETG-HF, a 0.4 mm nozzle, 0.20 mm layers, 5 walls, 6 top/bottom layers and 35% gyroid. These are starting parameters, not a validated profile. The 3MF files are geometry-only imports, not Bambu Studio projects or sliced jobs.

Inspect every layer in Bambu Studio. Use removable local support under the basket-root bridge, mounting ledges and dock tongue where the preview needs it. Keep guide surfaces clean. Do not leave support trapped behind the latch. Avoid high-acceleration modes on the tall chassis. Test a dock and unloaded rail fit first; nominal width clearance is 0.40 mm **per side**, and actual extrusion accuracy matters. Do not force a tight rail or flexure.

Source-solid volumes are approximately 120.5 cm³ chassis and 37.5 cm³ dock. At an assumed 1.28 g/cm³ this is about 202 g fully solid, excluding foam and hardware; actual sliced mass will differ. Shaft bores target 6.5 mm shafts with 0.20 mm interference. PETG clip retention, creep and fatigue are unqualified. Five positions do not guarantee that five arbitrary broadheads fit: actual blade shape, clocking, cutting width, foam and tip containment must be checked.

## Validation and limits

`geometry_checks.json` contains the exact STEP hashes, per-part dimensions/volumes, STEP round-trip comparison, manifold-STL checks, seven continuous rim sections, all five port/clip probes, direct spine-root checks, zero seated hard interference, and screw-driver clearance checks. The guide motion is sampled at 1 mm steps from 0 to 84 mm lift; intentional contact with the undeflected flexible tooth is recorded separately. This is not a dynamic contact or fatigue simulation.

`harness_checks.json` records text-to-CAD inspection, coordinate datums and per-solid soundness checks. `Images/` holds reviewed primary-STEP screenshots, including unloaded views; `snapshot_results.json` identifies the current packet. Assembly uses its seated bow frame; individual dock STEP/STL/3MF uses the rotated manufacturing frame described above.

No bow CAD or measured sight/rest envelopes were invented. No FEA was rerun for this revision, and earlier topology/FEA reports do not apply to the modified basket or mounting flange. Real bow fit, bolt seating, printed strength, broadhead containment, release force, clip retention, heat, UV, creep, impact and cycling remain open qualification work. Print and test a pilot before ordering or running 10,000 units. Two printed parts reduce assembly, but damaged integral clips require chassis replacement.

## Files and rebuild

- `LiftX_Quiver_LH.FCStd`: native assembly with shaft/foam reference geometry. References are not validated purchased parts.
- `STEP/LiftX_Quiver_Assembly.step`: seated assembly without arrows/foam.
- `STEP/`, `STL/`, `3MF/`: chassis, dock and optional gauge; dimensions in mm.
- `../lift_x_quiver_generator.py`: canonical FreeCAD/OCC source, including print-frame transforms.
- `check_design.py`, `harness_review.py`, `snapshot_jobs.json`: repeatable verification.
- `LiftX_LH_MountV2_Print_Pack.zip`: current files only, preserving folder structure.

From the repository root:

```powershell
& 'C:\Program Files\FreeCAD 1.1\bin\python.exe' Quiver/LiftX/lift_x_quiver_generator.py
& 'C:\Program Files\FreeCAD 1.1\bin\python.exe' Quiver/LiftX/MountV2/check_design.py
python Quiver/LiftX/MountV2/harness_review.py
python Quiver/LiftX/MountV2/package_release.py
```
