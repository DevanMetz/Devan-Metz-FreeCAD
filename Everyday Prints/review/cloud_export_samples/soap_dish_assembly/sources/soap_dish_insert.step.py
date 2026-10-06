"""Print the slotted plate down, feet up; turn over to use. Units mm."""
from soap_dish_common import PARAMETERS, build_insert as build


def gen_step():
    return build(**PARAMETERS)
