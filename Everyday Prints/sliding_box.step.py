"""Sliding-lid box; edit sliding_box_common.py to resize the set. mm."""
from sliding_box_common import PARAMETERS, build_box as build


def gen_step():
    return build(**PARAMETERS)
