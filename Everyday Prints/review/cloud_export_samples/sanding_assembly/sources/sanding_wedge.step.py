"""Print two tapered paper wedges for sanding_block.step.py. mm."""
from sanding_common import PARAMETERS, build_wedge as build


def gen_step():
    return build(**PARAMETERS)
