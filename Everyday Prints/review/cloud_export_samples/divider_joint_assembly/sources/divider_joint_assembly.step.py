"""Divider joint with separate reference board ends; assembly is view-only."""
from math import cos, radians, sin

from build123d import Align, Box, Color, Location
from cadgen.assembly import AssemblyHelper
from divider_joint_common import PARAMETERS as SHARED, build as build_joint, dimensions, settings

PARAMETERS = SHARED | dict(reference_length=80.0, reference_height=50.0)


def build(*, reference_length=80.0, reference_height=50.0, **overrides):
    p = settings(overrides)
    if not (p['insertion_depth']+20 <= reference_length <= 200
            and p['height']-p['floor']+10 <= reference_height <= 120):
        raise ValueError("Reference boards must extend beyond the branch and above the connector.")
    _, hub, _ = dimensions(p)
    assembly = AssemblyHelper("divider_joint:printed_connector_and_reference_boards")
    root = assembly.add(build_joint(**p), "printed_joint")
    for angle in p['ports']:
        board = assembly.add(Box(reference_length, p['board_thickness'], reference_height,
                                 align=(Align.MIN, Align.CENTER, Align.MIN)),
                             f"REFERENCE_board_{angle}_not_for_printing", color=Color(.66, .70, .71))
        theta = radians(angle)
        fixed = assembly.rigid_frame(root, f"backstop_{angle}",
                                     Location((hub/2*cos(theta), hub/2*sin(theta), p['floor']),
                                              (0, 0, angle)))
        moving = assembly.rigid_frame(board, "end_bottom_center", Location())
        assembly.face_to_face(fixed, moving, label=f"board_seated_at_{angle}")
    return assembly.build()


def gen_step():
    return build(**PARAMETERS)
