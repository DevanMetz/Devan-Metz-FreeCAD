"""Desk-clip microphone holder - parametric build123d generator.

Coordinate convention (mm):
    Z up, Y = out from desk edge toward user, X = lateral.
    Desktop surface = Z0; desk slab occupies Z -17..0 at Y <= 0.
    The clamp snaps onto the desk edge; the arm rises to a collet ring
    that friction-holds the mic with its axis along Y (capsule facing user).

Construction: one fused solid - C-clamp profile extruded in X, plus
column, boom, gusset, collet ring; slit + bore cut last.
"""

from build123d import (
    BuildLine,
    BuildSketch,
    Plane,
    Polyline,
    Box,
    Cylinder,
    Rot,
    Pos,
    extrude,
    fillet,
    make_face,
)
from cadgen import srgb

# ---------------------------------------------------------------- parameters
DESK_T = 17.0        # measured desk thickness
PRELOAD = 0.8        # relaxed mouth = DESK_T - PRELOAD -> spring grip
MOUTH = DESK_T - PRELOAD            # 16.2 relaxed jaw gap
CLAMP_W = 26.0       # clamp width (X) - narrower = more spring compliance
ARM_T = 4.0          # top arm thickness (rests on desktop)
JAW_T = 5.0          # bottom arm thickness
TOP_ARM_LEN = 30.0   # top arm reach back onto desktop (Y)
BOT_ARM_LEN = 26.0   # bottom arm reach back under desk (Y)
SPINE_OUT = 14.0     # spine outer face (+Y), hangs in front of desk edge
SPINE_IN = 10.0      # spine inner face (-Y side of throat)

COL_W = 18.0         # column width (X)
COL_T = 8.0          # column thickness (Y), sits on SPINE_IN..SPINE_OUT
COL_TOP = 91.0       # column top; 1 mm into boom body for a solid fuse
BOOM_BOT = 90.0      # boom underside
BOOM_TOP = 98.0      # boom top; 1.05 mm below bore floor (99.05) so the bore cut never reaches it
BOOM_TIP = 64.0      # boom +Y end; buries ~10 mm into the ring's solid bottom dome

MIC_D = 42.0
RING_ID = MIC_D - 0.1               # 41.9 collet bore (light interference)
RING_WALL = 3.45
RING_RO = RING_ID / 2 + RING_WALL   # 24.4 outer radius
RING_W = 16.0        # ring width along its axis (Y)
SLIT_W = 2.2         # collet slit width (X), cut at ring top
CRADLE_Y = 62.0      # ring center reach from desk edge
CRADLE_Z = 120.0     # ring center height above desktop
CRADLE_TOP = CRADLE_Z + RING_RO      # top of the ring (144.4)

COLOR = "#37474F"

# ------------------------------------------------------------- C-clamp body
# Closed profile in the YZ plane (Plane.YZ: sketch x -> global Y, y -> global Z)
_pts = [
    (-TOP_ARM_LEN, ARM_T),          # top arm tip, top
    (SPINE_OUT, ARM_T),             # spine outer, top
    (SPINE_OUT, -(MOUTH + JAW_T)),  # spine outer, bottom
    (-BOT_ARM_LEN, -(MOUTH + JAW_T)),  # bottom arm tip, bottom
    (-BOT_ARM_LEN, -MOUTH),         # bottom arm tip, top
    (SPINE_IN, -MOUTH),             # throat floor inner
    (SPINE_IN, 0.0),                # throat ceiling inner
    (-TOP_ARM_LEN, 0.0),            # top arm tip, underside
]

with BuildSketch(Plane.YZ) as prof:
    with BuildLine():
        Polyline(*_pts, close=True)
    make_face()
clamp = extrude(prof.sketch, amount=CLAMP_W / 2, both=True)

# ------------------------------------------------- column, boom, saddle post
column = Pos(0, (SPINE_IN + SPINE_OUT) / 2, (2.0 + COL_TOP) / 2) * Box(
    COL_W, COL_T, COL_TOP - 2.0
)
boom = Pos(0, (11.0 + BOOM_TIP) / 2, (BOOM_BOT + BOOM_TOP) / 2) * Box(
    COL_W, BOOM_TIP - 11.0, BOOM_TOP - BOOM_BOT
)

# ------------------------------------------------------------ collet ring
ring = Pos(0, CRADLE_Y, CRADLE_Z) * Rot(90, 0, 0) * Cylinder(RING_RO, RING_W)
bore = Pos(0, CRADLE_Y, CRADLE_Z) * Rot(90, 0, 0) * Cylinder(RING_ID / 2, RING_W * 2)
slit = Pos(0, CRADLE_Y, CRADLE_Z + RING_ID / 2 + RING_WALL / 2) * Box(
    SLIT_W, RING_W * 2.5, RING_WALL + 4.0
)

part = clamp + [column, boom, ring]
part = part - [slit, bore]
solid = part.solid()
solid.color = srgb(COLOR)

# --------------------------------------------------------- self checks
bb = solid.bounding_box()


def _check():

    errs = []
    if abs(bb.min.X + RING_RO) > 0.05 or abs(bb.max.X - RING_RO) > 0.05:
        errs.append(f"X bounds {bb.min.X:.2f}..{bb.max.X:.2f} (expect +-{RING_RO})")
    _y_hi = max(BOOM_TIP, CRADLE_Y + RING_W / 2)
    if abs(bb.min.Y + TOP_ARM_LEN) > 0.05 or abs(bb.max.Y - _y_hi) > 0.05:
        errs.append(f"Y bounds {bb.min.Y:.2f}..{bb.max.Y:.2f} (expect {-TOP_ARM_LEN}..{_y_hi})")
    if abs(bb.min.Z + (MOUTH + JAW_T)) > 0.05 or abs(bb.max.Z - CRADLE_TOP) > 0.05:
        errs.append(f"Z bounds {bb.min.Z:.2f}..{bb.max.Z:.2f} (expect {-(MOUTH + JAW_T)}..{CRADLE_TOP})")
    vol = solid.volume / 1000.0
    if not (25.0 < vol < 90.0):
        errs.append(f"volume {vol:.1f} cm^3 outside 25..90")
    if not solid.is_valid:
        errs.append("solid invalid")
    if errs:
        raise ValueError("self-check failed: " + "; ".join(errs))
    print(
        f"[mic_desk_mount] OK bbox {bb.size.X:.1f}x{bb.size.Y:.1f}x{bb.size.Z:.1f} mm,"
        f" volume {vol:.1f} cm^3"
    )


_check()


def gen_step():
    return solid
