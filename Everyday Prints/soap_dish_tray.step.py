"""Print the soap catch tray floor down. Edit shared soap_dish_common.PARAMETERS."""
from soap_dish_common import PARAMETERS, build_tray as build


def gen_step():
    return build(**PARAMETERS)
