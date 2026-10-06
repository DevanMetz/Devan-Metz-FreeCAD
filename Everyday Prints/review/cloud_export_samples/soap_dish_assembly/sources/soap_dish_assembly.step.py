"""Assembled soap dish for review, not a single printable object. Units mm."""
import importlib.util
from pathlib import Path
from build123d import Location
from cadgen.assembly import AssemblyHelper
from soap_dish_common import PARAMETERS, settings

ROOT = Path(__file__).resolve().parent


def source(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.step.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(**overrides):
    p = settings(overrides)
    assembly = AssemblyHelper("soap_dish:removable_drain_plate_on_four_feet")
    tray = assembly.add(source("soap_dish_tray").build(**p), "catch_tray")
    insert = assembly.add(source("soap_dish_insert").build(**p), "removable_drain_insert")
    floor_frame = assembly.rigid_frame(tray, "inside_floor", Location((0, 0, p['floor'])))
    # The moving frame flips the print about Y so the four feet point down;
    # the finger notch stays on the same +Y side as the tray's pouring notch.
    feet_frame = assembly.rigid_frame(insert, "feet_contact_plane",
                  Location((0, 0, p['plate']+p['foot_height']), (0, 180, 0)))
    assembly.face_to_face(floor_frame, feet_frame, label="feet_rest_on_tray_floor")
    return assembly.build()


def gen_step():
    return build(**PARAMETERS)
