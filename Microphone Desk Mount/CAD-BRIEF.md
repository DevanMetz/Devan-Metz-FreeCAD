# CAD Brief: Desk-Clip Microphone Holder

## Inputs
- Desk thickness: **17 mm** (clamp jaw gap = 17.8 mm, +0.8 mm print tolerance)
- Mic diameter: **42 mm** (cradle inner Ø 42.4, snap-in lip Ø 40.2, retention ring Ø 39.6)
- Mount height: mic center ≈ **120 mm** above desktop (user-selected)

## Part (single printable piece, no hardware)
- Spring C-clamp for desk edge: fixed top jaw + live bottom lever on a torsion pivot.
- Vertical arm column rising from the clamp top; horizontal reach over the desktop edge.
- Snap-in cradle at the end of the arm: 3/4 shell ring, two internal snap lips, front gap.

## Coordinate convention
- Z up, Y out from desk edge toward user, X lateral.
- Desktop surface = Z0; desk slab occupies Z −17…0 behind Y<0 plane.
- Clamp body top face flush with desktop (Z0); arm rises to cradle center Z=120.

## Parameters (named in source)
DESK_T=17.0, JAW_CLEAR=0.8, MIC_D=42.0, CRADLE_INNER_D=42.4,
LIP_D=40.2, RING_D=39.6, ARM_REACH=60, CRADLE_Z=120, WALL=2.4

## Output paths
- Generator: `Microphone Desk Mount/mic_desk_mount.step.py`
- STEP: `Microphone Desk Mount/mic_desk_mount.step`
- STL: `Microphone Desk Mount/mic_desk_mount.stl`

## Validation targets
1. Jaw gap measures 17.8 ±0.05 mm (inspect measure)
2. Cradle ID measures 42.4 ±0.05 mm
3. Retention-ring opening measures 39.6 ±0.05 mm
4. Cradle center Z = 120 ±0.5 mm
5. `inspect validate` passes (closed solids)
6. Snapshot review confirms: open mouth ≥ desk thickness, lips point down, gap faces user, single connected solid
