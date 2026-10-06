"""Sanding block in print orientation; dimensions in sanding_common.py. mm."""
from sanding_common import PARAMETERS, build_block as build


def gen_step():
    return build(**PARAMETERS)
