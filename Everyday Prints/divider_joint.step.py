"""Selectable cross, T, corner, or straight drawer-divider joint."""
from divider_joint_common import PARAMETERS, build


def gen_step():
    return build(**PARAMETERS)
