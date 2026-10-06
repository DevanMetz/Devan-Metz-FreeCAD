"""Lid for sliding_box; print its broad face down and pull grip up. mm."""
from sliding_box_common import PARAMETERS, build_lid as build


def gen_step():
    return build(**PARAMETERS)
