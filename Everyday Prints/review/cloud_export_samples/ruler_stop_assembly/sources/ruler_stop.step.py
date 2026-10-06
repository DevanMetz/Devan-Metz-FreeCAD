"""Print an end profile down; rotate for use with the ruler. mm."""
from ruler_stop_common import PARAMETERS, build_body as build


def gen_step():
    return build(**PARAMETERS)
