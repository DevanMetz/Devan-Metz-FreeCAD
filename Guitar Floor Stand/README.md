# Organic Topology Guitar Stand

A one-piece stand generated around a stable 3D ground structure. Twelve sizing
iterations redistribute rib area for vertical, rearward, and both lateral load
cases before Gaussian field blending melts the paths into a continuous organic
skin and carves out the padded guitar envelope.
The high-resolution STL is watertight; the FreeCAD file also contains a hidden
faceted solid used for STEP export and analysis.

## Dimensions

| Dimension | Value |
|---|---:|
| Guitar body | 45 mm |
| Minimum padded envelope | 51 mm |
| Padding allowance | 3 mm per face |
| Guitar body / padding | 45 mm / 3 mm per face |
| Footprint | 234 x 234 mm |
| Height | 181 mm |

## Print and use

- Print upright with the 234 x 234 mm base on the bed and organic/tree supports
  from the build plate under the steepest blended branches.
- Use PETG or ASA, 5 walls, 5 top/bottom layers, and 25% gyroid infill.
- Add 3-7 mm adhesive felt or closed-cell EVA to the seats, front lips, and
  backrest contact areas; trim the foam for a stable fit before use.
- Test the stand low over a rug first. Do not use it where children, pets, or
  foot traffic can knock the guitar sideways.

The editable FreeCAD dimensions are stored on the `Parameters` object. Run
`make_guitar_stand.py` with FreeCADCmd to regenerate the FCStd and STL files.

`topology-side.png` preserves the earlier 2D SIMP study; the current model uses
the 3D force-sized cellular generator in `make_guitar_stand.py`.

## Simulation results

- Smooth 101,136-facet print skin around the multi-load optimized paths; solid
  volume is 583,956 mm3, 31% below the previous blob-frame version.
- Final-solid CalculiX check: 213,969 tetrahedra, isotropic PETG at 2 GPa,
  150 N downward plus simultaneous 50 N rearward and 50 N lateral loads.
- Maximum displacement: 0.813 mm. Maximum von Mises stress: 7.58 MPa, giving
  2.6x margin against a conservative 20 MPa printed-part design allowable.
- A 59 mm modeling keep-out fully contains the required 51 mm padded,
  12-degree-leaning guitar envelope.

The FEA treats the print as solid isotropic PETG and the floor as fixed. It is a
design check, not certification of layer adhesion or resistance to being knocked
over; physically test the first print low over a rug.
