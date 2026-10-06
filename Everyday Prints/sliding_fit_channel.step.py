"""Print with sliding_fit_slider to tune guide clearance before the full box. mm."""
from sliding_box_common import PARAMETERS, build_fit_channel as build


def gen_step():
    return build(**PARAMETERS)
