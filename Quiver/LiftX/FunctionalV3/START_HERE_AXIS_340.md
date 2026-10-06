# Your configuration: left-handed LIFT X + Easton AXIS 340

**Fit-test prototype only. Bow interface and physical retention are not verified. Do not shoot with this mount yet.**

1. Print `STL/axis_sizing_coupon.stl` in TPU 95A. Trial the sample marked with **four dots** against an actual bare shaft. AXIS 340 listed OD: 6.7818 mm. Fit depends on filament and printer calibration.
2. If fit/release are appropriate, print **one each**:
   - `STL/lower_frame.stl` — PETG, carrier on bed.
   - `STL/upper_hood.stl` — PETG, cap on bed.
   - `STL/gripper_axis_340.stl` — TPU, flat face down, pegs last.
   - `STL/provisional_dock.stl` — PETG, back face down; bow-fit verification required before structural use.
3. Read `README.md` for support/bridge locations, foam, two M4 fasteners, broadhead limits and physical-test gates. Geometry-only equivalents are in `3MF/`; these are not sliced printer jobs.

Do not print the assembly, loaded arrow envelopes, cutaway, foam template or hardware references. Other gripper sizes are alternatives, not parts you need.

Broadhead target: at most 35 mm diameter × 70 mm length in the stored configuration. Passing the sampled CAD clearance tests is not proof of blade containment, grip force, strength or actual bow clearance.
