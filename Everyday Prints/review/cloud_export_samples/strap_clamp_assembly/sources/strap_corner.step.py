"""Strap-clamp corner pad. Print four, lower guide lip on the bed. Units mm."""
from strap_corner_common import PARAMETERS,build


def gen_step():
    return build(**PARAMETERS)
