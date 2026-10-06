# LIFT X LH / Easton AXIS — Functional V3 prototype

This replaces the rejected MountV2 loading geometry. It is a fit-test prototype, not a verified Mathews accessory or production release.

## User requirements

- Left-handed Mathews LIFT X, Spot-Hogg through-riser/dovetail sight (exact model unconfirmed), QAD MX2 UltraRest.
- Easton AXIS **340**, confirmed by the user. Do not confuse the nominal 5 mm bore class with shaft outside diameter.
- Five arrows; ordinary fixed broadheads and closed mechanicals within a stated storage envelope. Broadheads themselves are reference envelopes, not manufactured parts.
- Mostly FDM printed, minimal distinct parts and assembly, all individual pieces fit a 256 mm Bambu A1 build volume.
- Direct structural hood/spine union, enclosed hood sides and cap, no ornamental diagonal connectors or hard holes trapping complete arrows.

## Design decisions and coordinates

- +Z points toward arrow tips. Model construction is in an unmirrored frame with extraction toward +Y; final LH assembly mirrors Y. The bow is on the opposite side of extraction.
- A downward-opening protective hood replaces the former upward-opening basket. The open mouth faces the shaft grippers. This corrects the loading failure rather than preserving the misleading earlier 'open top' orientation.
- Five staggered axes on a 44 mm equilateral pitch. Design envelope per head: 35 mm diameter x 70 mm length, including ferrule/blades in their STORED configuration.
- Four distinct printed components: upper hood/spine, lower spine/carrier, replaceable TPU gripper, provisional sliding dock. Foam is a cut consumable. Two M4 fasteners join the spine halves.
- Approximate assembled height 360 mm; individual rigid frame pieces below 230 mm. A short assembled quiver was not traded against a practical hood-to-gripper separation.
- Conventional solid webs and tapered transitions; no claim of topology-optimized strength. All elastic retention, vibration, blade containment, creep and impact performance require physical testing.
- The mount's generic accessory-hole template is NOT verified as exposed/compatible on this bow. OEM LowPro interface dimensions are not available. No invented OEM fit claim.

## AXIS gripper variants

Manufacturer outside diameters: 600 .253 in (6.4262 mm), 500 .258 (6.5532), 400 .264 (6.7056), 340 .267 (6.7818), 300 .275 (6.9850), 260 .280 (7.1120), 200 .286 (7.2644).

One gripper variant is used per assembly: the user-confirmed **340** (6.7818 mm shaft OD). TPU bore interference is initially 0.25 mm on diameter; fit and release force must be tested with the actual filament and shaft. A sizing coupon precedes printing a complete gripper. The fourth, four-dot coupon sample is the 340 starting point.

Sources: https://eastonarchery.com/arrows_/5mm-axis-carbon-arrows/ ; https://shop.g5outdoors.com/products/montec ; https://mathewsinc.com/products/lowpro-detachable-quiver . A 35 mm storage envelope exceeds the listed 1–1 1/8 in Montec cutting diameters but does not establish fit for every broadhead, head length, or blade orientation.

## Validation and release gates

1. Valid, positive-volume, single-solid manufacturing parts; STEP plus watertight print-oriented mesh exports.
2. Explicit mouth direction, cavity dimensions, head spacing, grip alignment and spine joint clearances.
3. Sampled full-arrow extraction against hard parts and four neighboring arrows, using 35 x 70 mm conservative head cylinders and maximum AXIS shaft OD. Foam/gripper elastic contact excluded and reported.
4. Multi-view CAD snapshots reviewed, including underside and loaded reference.
5. Print-envelope check, overhang review, and honest support/orientation notes; bounding-box fit alone is not print validation.
6. Physical gates: shaft retention/release, broadhead clearance/containment, dock fit, bow/cable/rest/sight clearance throughout draw cycle, fastener retention, pull/vibration/drop/environmental tests. Do not shoot with an unvalidated mount or use exposed sharp heads for early testing.

STEP-first build123d source is canonical. Existing FreeCAD designs are preserved. The step-parts catalog/tool was searched and is unavailable; no downloaded supplier geometry is substituted or guessed.
