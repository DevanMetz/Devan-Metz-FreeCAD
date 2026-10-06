"""Matching ruler-stop wedge; print its broad flat lower face down. mm."""
from ruler_stop_common import PARAMETERS, build_wedge as build


def gen_step():
    return build(**PARAMETERS)
