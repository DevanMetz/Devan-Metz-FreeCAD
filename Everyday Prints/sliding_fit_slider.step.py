"""Short matching lid profile for sliding_fit_channel. mm."""
from sliding_box_common import PARAMETERS, build_fit_slider as build


def gen_step():
    return build(**PARAMETERS)
