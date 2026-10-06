# 3-tier bathroom corner shelf

Designed around one **8 x 300 mm carbon-fiber rod** and three identical
quarter-circle shelves with **185 mm wall lengths**.

Each shelf uses a **5 mm square grate on a 20 mm pitch** with a continuous
5 mm perimeter, so water drains freely while the retaining lips and rod hub
remain supported.

The front underside and hub are filleted; lip tops, rod entry,
spacers, and cap have small chamfers to remove sharp edges and ease assembly.
The two exposed outer shelf corners have 5 mm plan-view chamfers with full
3 mm retaining-wall thickness. The rear wall uses a matched 8 mm outside
radius and 5 mm inside radius, so the curve keeps the same 3 mm thickness and
clears typical caulk or grout. The 0.8 mm inner lip chamfer continues around
the rear fillet without a sharp transition.

## Print

- `shelf.stl`: print 3, flat side down
- `spacer.stl`: print 4, upright
- `top_cap.stl`: print 1, open side down
- PETG is recommended for a wet bathroom; 4 walls and 20% infill are enough
  for normal toiletries.

The modeled rod hole is 8.2 mm. If your printer makes holes tight, use an
8.2 mm drill by hand after printing or increase `FIT_CLEARANCE` in
`make_corner_shelf.py` and rebuild.

## Assemble

Slide onto the rod in this order:

1. shelf
2. two spacers
3. shelf
4. two spacers
5. shelf
6. top cap

The shelves sit at 0, 140, and 280 mm. Their corner hubs provide 16 mm of
bearing surface so the single rod acts as a stiff spine. Use the organizer
with both straight edges against the bathroom corner; it is intended for
soap, bottles, and similar light counter items, not heavy cantilevered loads.

Open `Bathroom Corner Shelf.FCStd` to inspect the assembly. Edit the constants
at the top of `make_corner_shelf.py` and rerun it with FreeCAD's Python to
regenerate the model and STLs.
