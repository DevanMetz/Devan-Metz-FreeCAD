# Four-arrow carbon-spine hunting quiver

The generated design puts two parallel 4 × 300 mm carbon rods directly behind the arrow row at 10 mm centre spacing. The minimalist hood and centre mount clamp both rods; the TPU gripper uses interference-fit sockets.

## Print

| Part | Material | Walls | Infill | Orientation |
|---|---|---:|---:|---|
| `hood_petg.stl` | ASA, PETG, or PA-CF | 3 | 15% gyroid | closed crown on bed |
| `hood_rod_cap_petg.stl` | ASA, PETG, or PA-CF | 6 | 45% gyroid | broad flat face on bed |
| `shaft_gripper_tpu.stl` | TPU 95A | 4 | 35% gyroid | gripper bar on bed |
| `bow_mount_petg.stl` | ASA, PETG, or PA-CF | 5 | 35% gyroid | broad flat face on bed |
| `bow_mount_cap_petg.stl` | ASA, PETG, or PA-CF | 5 | 35% gyroid | broad flat face on bed |

Use 0.20 mm layers and five top/bottom layers. Do not use PLA for a hunting quiver that may sit in a hot vehicle. The STLs are exported at 0.08 mm chord tolerance.

## Hardware and assembly

- 2 × 4 × 300 mm carbon-fibre rods
- 2 × M3 heat-set inserts and M3 × 14 mm screws for the hood clamp
- 2 × M3 × 16 mm screws, washers, and nyloc nuts for the centre rod clamp
- 2 existing bow-quiver bolts with washers, up to 5 mm diameter
- 97 × 41 × 22 mm block of firm closed-cell broadhead foam

Deburr the rod ends. Press both rods 28 mm into the TPU gripper, then clamp the hood onto the opposite ends. Position the centre mount and tighten only until the rods cannot slip by hand. Do not crush the carbon rods; 0.7 N·m is a reasonable ceiling for the M3/M4 clamp screws.

The bow-side capsule slot accepts two bolts with approximately 10–38 mm centre spacing. Verify clearance from the bowstring, cables, limb, sight, and rest through the complete draw cycle before field use.

## Fit changes

Edit `ROD_DIAMETER`, `ROD_SPACING`, `ARROW_DIAMETER`, or `BOW_BOLT_DIAMETER` at the top of `pro_quiver_generator.py`, then regenerate with:

```powershell
& 'C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe' '.\pro_quiver_generator.py'
```

The default TPU pockets fit 6.5 mm shafts. Print the gripper first and adjust `TPU_GRIP_INTERFERENCE` if retention is too tight or loose. Broadheads must be fully buried in firm foam and must not touch the printed shell.
