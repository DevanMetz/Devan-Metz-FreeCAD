"""Functional CAD probes, parameter cases, and checks of delivered print meshes."""
import importlib.util
import hashlib
import json
from math import pi, cos, sin, radians, sqrt, asin
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent
DIVIDER_T = dict(board_thickness=2,clearance=.3,wall=2,insertion_depth=12,
                  height=14,floor=2,lead_in=.3,ports=(0,90,180))
DIVIDER_CORNER = dict(board_thickness=6,clearance=.8,wall=3,insertion_depth=24,
                       height=26,floor=3,lead_in=.8,ports=(0,90))
STRAP_COMPACT = dict(leg_length=22,wall=5,corner_relief=2.4,strap_width=12,
                     strap_thickness=1,width_clearance=1.6,lip_projection=1.6,lip_thickness=1.6)
STRAP_LARGE = dict(leg_length=45,wall=8,corner_relief=4,strap_width=38,
                   strap_thickness=1.8,width_clearance=3,lip_projection=2.8,lip_thickness=2.8)
REDUCER_COMPACT = dict(large_diameter=30,small_diameter=18,large_clearance=.3,
                       small_clearance=.2,wall=2,large_depth=12,small_depth=10,
                       transition_length=16,stop_inset=1.4,lead_in=.4)
REDUCER_LARGE = dict(large_diameter=80,small_diameter=50,large_clearance=.8,
                     small_clearance=.6,wall=3.2,large_depth=32,small_depth=28,
                     transition_length=45,stop_inset=2.8,lead_in=.8)
RULER_COMPACT = dict(ruler_width=20,ruler_thickness=.8,side_clearance=.3,body_length=20,
                     floor=2.4,roof=3,side_wall=3,clamp_gap=1.8,wedge_length=30,wedge_tip=.6,
                     wedge_back=2.6,wedge_side_clearance=.9,grip_length=3,grip_height=3)
RULER_LARGE = dict(ruler_width=35,ruler_thickness=1.5,side_clearance=.6,body_length=30,
                   floor=4,roof=5,side_wall=5,clamp_gap=3,wedge_length=45,wedge_tip=1.2,
                   wedge_back=4,wedge_side_clearance=1.4,grip_length=5,grip_height=5)
SLIDING_COMPACT = dict(length=80,width=55,height=24,wall=2,floor=2,lid_thickness=2,
                       side_clearance=.25,vertical_clearance=.25,roof=1.4,ledge_inset=3,
                       end_clearance=.3,pull_extension=4,sample_length=22,sample_height=12)
SLIDING_LARGE = dict(length=170,width=120,height=55,wall=3,floor=3,lid_thickness=3.2,
                     side_clearance=.5,vertical_clearance=.4,roof=2.4,ledge_inset=4,
                     end_clearance=.6,pull_extension=8,sample_length=36,sample_height=20)
SLIDING_BAD = dict(side_clearance=1,lid_thickness=1.8,vertical_clearance=.2)
SANDING_COMPACT = dict(length=75,width=38,height=22,end_margin=6,slot_width=5,slot_span=30,
                       slot_depth=13,paper_thickness=.2,wedge_tip=2.8,wedge_top=6.6,
                       wedge_height=18,wedge_end_clearance=1.6)
SANDING_LARGE = dict(length=160,width=80,height=38,end_margin=10,slot_width=8,slot_span=68,
                     slot_depth=23,paper_thickness=.5,wedge_tip=4,wedge_top=11,
                     wedge_height=28,wedge_end_clearance=3)
CASES = {
    "divider_joint": [(40.2,40.2,18),DIVIDER_T,DIVIDER_CORNER,{"ports":(0,90,90)}],
    "sorting_sieve": [(135,90,18),
                      {"bowl_diameter":60,"height":12,"wall":2,"floor":2,"hole_diameter":2.4,
                       "pitch":5,"hole_margin":3,"handle_length":35,"handle_width":14,
                       "handle_thickness":3,"hanging_hole":3.2},
                      {"bowl_diameter":120,"height":24,"wall":3,"floor":3,"hole_diameter":8,
                       "pitch":12,"hole_margin":5,"handle_length":60,"handle_width":24,
                       "handle_thickness":5,"hanging_hole":6},
                      {"hole_diameter":6}],
    "sieve_aperture_coupon": [(40,18,2.4),{"hole_diameter":2.4,"floor":2},
                              {"hole_diameter":8,"floor":3,"offsets":(-.4,-.2,0,.2,.4)},
                              {"offsets":(.2,0,-.2)}],
    "strap_corner": [(38,38,33.5),STRAP_COMPACT,STRAP_LARGE,{"strap_thickness":2}],
    "tube_reducer": [(55.2,55.2,72),REDUCER_COMPACT,REDUCER_LARGE,{"transition_length":12}],
    "socket_fit_ring": [(55.2,55.2,8),
                        {"tube_diameter":18,"clearance":.2,"wall":2,"height":6,"lead_in":.4},
                        {"tube_diameter":80,"clearance":.8,"wall":3.2,"height":12,"lead_in":.8},
                        {"wall":2,"lead_in":1.2}],
    "ruler_stop": [(34.4,10.2,24),RULER_COMPACT,RULER_LARGE,{"clamp_gap":2.6}],
    "ruler_wedge": [(35,24,7),RULER_COMPACT,RULER_LARGE,{"clamp_gap":2.6}],
    "workshop_scoop": [(110,45,20),
                       {"bowl_length":45,"bowl_width":32,"height":14,"wall":2,"floor":2,
                        "corner_radius":4.5,"handle_length":35,"handle_width":14,"handle_thickness":3,
                        "pour_width":12,"pour_drop":3,"hanging_hole":3.5},
                       {"bowl_length":85,"bowl_width":65,"height":30,"wall":3,"floor":3.2,
                        "corner_radius":8,"handle_length":65,"handle_width":24,"handle_thickness":5,
                        "pour_width":24,"pour_drop":5,"hanging_hole":6},
                       {"pour_width":30}],
    "plant_marker": [(26,115,2.4),
                     {"label_width":20,"label_height":32,"stake_length":40,"stake_width":6,
                      "thickness":1.8,"tip_length":10,"tip_width":1,"corner_radius":2,
                      "neck_radius":1.2,"hanging_hole":3},
                     {"label_width":42,"label_height":65,"stake_length":105,"stake_width":12,
                      "thickness":3.2,"tip_length":22,"tip_width":1.6,"corner_radius":4,
                      "neck_radius":3,"hanging_hole":0},
                     {"label_width":20,"stake_width":12,"corner_radius":4,"neck_radius":3}],
    "bookend": [(130,80,130),
                {"front_depth":70,"back_depth":22,"width":60,"height":90,"floor":3,
                 "wall":3,"brace_height":60,"brace_width":3.2,"corner_radius":2.5},
                {"front_depth":140,"back_depth":40,"width":120,"height":170,"floor":5,
                 "wall":6,"brace_height":125,"brace_width":6,"corner_radius":4},
                {"brace_height":125}],
    "corner_cable_guide": [(41*sqrt(3)/2+6,41*sqrt(3)/2+6,10.4),
                          {"inside_radius":12,"channel_width":6,"channel_depth":6,
                           "floor":2,"wall":2,"tab_diameter":10,"mount_hole":3.2},
                          {"inside_radius":60,"channel_width":22,"channel_depth":16,
                           "floor":3.2,"wall":3,"tab_diameter":18,"mount_hole":5},
                          {"tab_diameter":10,"wall":4}],
    "marking_saddle": [(90,44.5,23),
                       {"length":60,"board_width":20,"clearance":.3,"wall":2.4,
                        "plate":2.4,"fence_height":12,"mark_width":.8},
                       {"length":170,"board_width":85,"clearance":.8,"wall":4,
                        "plate":4,"fence_height":35,"mark_width":1.3},
                       {"board_width":90}],
    "roll_adapter": [(60,60,17.4),
                     {"roll_bore":30,"axle_diameter":4,"axle_clearance":.4,
                      "insertion_depth":8,"hub_wall":2.4,"flange_extra":3,
                      "flange_thickness":2,"spoke_count":4,"spoke_thickness":2.4,"lead_in":.4},
                     {"roll_bore":80,"outer_clearance":.8,"axle_diameter":12,"axle_clearance":.8,
                      "insertion_depth":25,"wall":3,"hub_wall":4,"flange_extra":6,
                      "flange_thickness":3.2,"spoke_count":8,"spoke_thickness":4,"lead_in":.8},
                     {"roll_bore":25,"axle_diameter":20}],
    "hand_knob": [(40,12+14*sqrt(3),14),
                   {"grip_diameter":34,"lobe_radius":5,"height":10,"nut_af":7,
                    "nut_thickness":3.2,"nut_clearance":.2,"pocket_extra_depth":.3,
                    "bolt_diameter":4,"bolt_clearance":.4,"lead_in":.3,"valley_radius":.6},
                   {"grip_diameter":64,"lobe_radius":8,"height":24,"nut_af":17,
                    "nut_thickness":8,"nut_clearance":.6,"pocket_extra_depth":.7,
                    "bolt_diameter":10,"bolt_clearance":.8,"lead_in":.6,"valley_radius":1.2},
                   {"nut_af":20}],
    "slotted_shim": [(40,24,2),
                      {"length":30,"width":18,"thickness":1,"bolt_diameter":4,
                       "clearance":.4,"slot_depth":20,"corner_radius":2,"hanging_hole":3.2},
                      {"length":70,"width":42,"thickness":8,"bolt_diameter":12,
                       "clearance":1,"slot_depth":46,"corner_radius":4,"hanging_hole":6},
                      {"slot_depth":35}],
    "fold_clip": [(50.4,10.8,12),
                   {"arm_length":30,"depth":8,"arm_thickness":1.8,"root_radius":2.5,
                    "jaw_gap":.4,"entry_flare":1.6,"nose_length":4,"nose_radius":.3},
                   {"arm_length":65,"depth":18,"arm_thickness":3.2,"root_radius":4,
                    "jaw_gap":1,"entry_flare":3,"nose_length":8,"nose_radius":.4},
                   {"entry_flare":3}],
    "cord_clip": [(20,6.5+sqrt(8.97),12),
                   {"cable_diameter":4,"clearance":.3,"capture":.5,"arm_thickness":.8,
                    "base_width":16,"base_thickness":2.4,"depth":8,"tip_radius":.15},
                   {"cable_diameter":10,"clearance":.8,"capture":1,"arm_thickness":1.4,
                    "base_width":28,"base_thickness":4,"depth":18,"tip_radius":.3},
                   {"cable_diameter":4,"capture":1.2}],
    "round_stock_cradle": [(80,60,30),
                            {"length":50,"width":44,"height":20,"apex_height":6,"mount_hole":3},
                            {"length":130,"width":90,"height":45,"apex_height":12,"mount_hole":5},
                            {"width":50}],
    "tie_anchor": [(26,26,8.6),
                    {"side":22,"tunnel_width":3.6,"straight_height":1.2,"roof":2,"mount_hole":3.2,"mount_inset":4.5},
                    {"side":40,"tunnel_width":8,"straight_height":3,"floor":3,"roof":4,"mount_hole":5,"mount_inset":7},
                    {"side":20}],
    "workshop_funnel": [(89,78,60),
                         {"mouth_diameter":40,"spout_diameter":8,"cone_height":24,"spout_length":12,
                          "wall":1.6,"rim_extra":1.5,"rim_height":2.4},
                         {"mouth_diameter":100,"spout_diameter":24,"cone_height":60,"spout_length":30,
                          "wall":3,"rim_extra":3,"rim_height":4,"hanger_hole":6},
                         {"cone_height":25}],
    "sliding_box": [(120,80,32),SLIDING_COMPACT,SLIDING_LARGE,SLIDING_BAD],
    "sliding_lid": [(123.2,74.6,5.4),SLIDING_COMPACT,SLIDING_LARGE,SLIDING_BAD],
    "sliding_fit_channel": [(30,80,16),SLIDING_COMPACT,SLIDING_LARGE,SLIDING_BAD],
    "sliding_fit_slider": [(36,74.6,5.4),SLIDING_COMPACT,SLIDING_LARGE,SLIDING_BAD],
    "parts_tray": [(150, 100, 24), {"length": 50, "width": 35, "height": 8, "rows": 1, "columns": 1},
                   {"length": 240, "width": 180, "height": 60, "rows": 4, "columns": 6}, {"columns": 1.5}],
    "cable_comb": [(59, 32, 4), {"cable_diameters": (1.5, 2), "clearance": .2, "web": 3, "mounting_hole": 2},
                   {"cable_diameters": (10, 12, 14), "clearance": 1.5, "slot_depth": 25, "depth": 40},
                   {"slot_depth": 30}],
    "divider_foot": [(34, 24, 20), {"board_thickness": 1, "clearance": .1, "height": 10, "jaw": 2, "lead_in": .4},
                     {"board_thickness": 10, "clearance": 1.2, "base_width": 50, "height": 45, "jaw": 6, "lead_in": 3},
                     {"base_width": 20, "board_thickness": 10}],
    "divider_fit_coupon": [(26, 20, 8), {"board_thickness": 1, "clearances": (.1, .2), "height": 6},
                           {"board_thickness": 10, "clearances": (.2, .4, .6, .8, 1, 1.2), "height": 15},
                           {"clearances": (-.1, .2)}],
    "phone_stand": [(85, 96, 65), {"depth": 70, "height": 65, "width": 40, "angle": 78},
                    {"depth": 130, "height": 140, "width": 100, "angle": 60}, {"depth": 60, "angle": 60}],
    "corner_square": [(80, 80, 8), {"leg": 40, "leg_width": 12, "thickness": 4, "corner_relief": 1},
                      {"leg": 160, "leg_width": 30, "thickness": 15}, {"leg": 40, "leg_width": 30}],
    "handle_marking_jig": [(160, 40, 18), {"hole_pitch": 16, "setback": 10, "end_margin": 8},
                           {"hole_pitch": 192, "setback": 70, "fence_height": 35}, {"fence_height": 7}],
    "tube_squeezer": [(90, 26, 6), {"length": 45, "width": 18, "thickness": 4, "slot_length": 25, "slot_gap": .8, "lead_in": .2},
                      {"length": 140, "width": 40, "thickness": 10, "slot_length": 115, "slot_gap": 4, "lead_in": 1.2},
                      {"slot_length": 88}],
    "soap_dish_tray": [(120, 84, 14), {"length": 80, "width": 60, "height": 12, "foot_height": 6},
                       {"length": 200, "width": 140, "height": 24, "foot_height": 16}, {"height": 10}],
    "soap_dish_insert": [(113.2, 77.2, 11), {"length": 80, "width": 60, "height": 12, "foot_height": 6},
                         {"length": 200, "width": 140, "height": 24, "foot_height": 16}, {"drain_margin": 10}],
    "label_stand": [(50, 24, 12), {"length": 30, "width": 16, "height": 7, "slot_depth": 4, "slot_gap": .4, "lean_angle": 0, "corner_radius": 2},
                    {"length": 90, "width": 40, "height": 24, "slot_depth": 18, "slot_gap": 2, "lean_angle": 25},
                    {"slot_depth": 11}],
    "paint_pyramid": [(50, 50, 26), {"base_size": 30, "height": 12, "base_thickness": 1.6, "tip_size": 1.2, "skirt": 2},
                      {"base_size": 80, "height": 45, "base_thickness": 4, "tip_size": 5, "skirt": 5},
                      {"base_size": 25, "skirt": 8, "tip_size": 6}],
    "cable_winder": [(95, 44, 4), {"length": 60, "width": 32, "neck_width": 14, "end_width": 12, "thickness": 2.4, "notch_gap": 2.6, "notch_depth": 5},
                     {"length": 140, "width": 60, "neck_width": 32, "end_width": 20, "thickness": 6, "notch_gap": 5, "notch_depth": 10},
                     {"length": 55, "end_width": 20}],
    "hex_bit_rack": [(80, 44, 14), {"columns": 2, "rows": 1, "pitch": 8, "margin": 6, "height": 8, "floor": 1.6, "shank_af": 3, "clearance": .2, "lead_in": .3},
                     {"columns": 8, "rows": 4, "pitch": 18, "margin": 12, "height": 24, "floor": 3, "shank_af": 10, "clearance": .5, "lead_in": 1},
                     {"pitch": 10}],
    "hex_bit_fit_coupon": [(40, 20, 14), {"shank_af": 3, "clearances": (.1,.3), "pitch": 8, "margin": 6, "depth": 16, "height": 8, "floor": 1.6, "lead_in": .3},
                           {"shank_af": 10, "clearances": (.1,.3,.5,.7,1), "pitch": 18, "margin": 12, "depth": 26, "height": 20, "floor": 3, "lead_in": 1},
                           {"pitch": 8}],
    "sanding_block": [(100,50,25), SANDING_COMPACT, SANDING_LARGE, {"slot_depth":10}],
    "sanding_wedge": [(8,36,20), SANDING_COMPACT, SANDING_LARGE, {"slot_depth":10}],
    "cable_grommet": [(34+sqrt(34**2-5**2),68,18.4),
                       {"hole_diameter":30,"flange_width":3,"insertion_depth":6,"opening":0,"lead_in":.3},
                       {"hole_diameter":90,"clearance":.8,"wall":3,"flange_width":6,
                        "flange_thickness":3,"insertion_depth":25,"opening":20,"lead_in":1},
                       {"hole_diameter":25,"opening":20}],
    "radius_template": [(80,80,3), {"side":60,"thickness":2,"radii":(3,6,9,12),"finger_hole":16},
                         {"side":120,"thickness":5,"radii":(10,20,30,40),"finger_hole":30},
                         {"radii":(5,10,15,45)}],
    "center_finder": [(100,24,16),
                       {"pin_spacing":45,"pin_diameter":6,"pin_height":7,"plate_width":18,
                        "plate_thickness":3,"end_margin":8,"mark_hole":2.6},
                       {"pin_spacing":140,"pin_diameter":12,"pin_height":20,"plate_width":32,
                        "plate_thickness":6,"end_margin":16,"mark_hole":5},
                       {"plate_width":14}],
    "brush_rest": [(100,150,20),
                    {"width":80,"length":120,"rim_height":10,"groove_diameters":(6,8),
                     "groove_pitch":24,"rail_height":16,"rail_spacing":30,"rear_inset":25},
                    {"width":140,"length":180,"wall":3,"floor":3,"rim_height":16,
                     "groove_diameters":(10,14,18,22),"clearance":1,"groove_pitch":32,
                     "rail_height":27,"rail_thickness":5,"rail_spacing":50},
                    {"rail_height":18}],
    "utility_peg": [(60,24,31),
                     {"mount_spacing":30,"end_margin":6,"plate_width":20,"plate_thickness":2.4,
                      "mount_hole":3.2,"peg_diameter":6,"peg_length":20,"head_diameter":12,"head_thickness":2},
                     {"mount_spacing":60,"end_margin":10,"plate_width":34,"plate_thickness":4,
                      "mount_hole":5.5,"peg_diameter":16,"peg_length":45,"head_diameter":24,"head_thickness":3},
                     {"head_diameter":10}],
}


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.step.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def close(actual, expected, tolerance=1e-5):
    if not np.allclose(actual, expected, rtol=0, atol=tolerance):
        raise AssertionError(f"Expected {expected}, got {actual}")


def sound(shape):
    assert shape.is_valid, "Invalid BREP"
    solids = shape.solids()
    assert len(solids) == 1, f"Expected one connected solid, found {len(solids)}"
    assert solids[0].volume > 0, "Non-positive volume"
    close(shape.bounding_box().min.Z, 0)
    return solids[0]


def contains(solid, point, expected):
    assert solid.is_inside(point) == expected, f"Unexpected material at {point}"


def default_features(name, shape):
    s = shape.solids()[0]
    if name == "divider_joint":
        return divider_joint_features(shape,load(name).PARAMETERS)
    if name == "sorting_sieve":
        return sieve_features(shape,load(name).PARAMETERS,97)
    if name == "sieve_aperture_coupon":
        return aperture_coupon_features(shape,load(name).PARAMETERS)
    if name == "strap_corner":
        for point,material in [((-.05,15,15),True),((.05,15,15),False),
                               ((15,-.05,15),True),((15,.05,15),False),
                               ((15,-5.95,15),True),((15,-6.05,15),False),
                               ((15,-7.95,1),True),((15,-8.05,1),False),
                               ((15,-7,1.95),True),((15,-7,2.05),False),
                               ((15,-6.95,30.25),True),((15,-7.05,30.25),False),
                               ((15,-7.95,32.5),True),((15,-8.05,32.5),False),
                               ((-4,-2,33.45),True),((-4,-2,33.55),False)]:
            contains(s,point,material)
        for angle in (3*pi/4,5*pi/4,7*pi/4):
            for radius,material in ((2.95,False),(3.05,True)):
                contains(s,(radius*cos(angle),radius*sin(angle),15),material)
        for radius,material in ((5.95,True),(6.05,False)):
            contains(s,(-radius/sqrt(2),-radius/sqrt(2),15),material)
        for z in (.1,15,33.4):
            contains(s,(0,0,z),False)
            contains(s,(1,1,z),False)
        faces = [f for f in s.faces() if abs(f.area-904.5)<1e-5]
        assert len(faces) == 2
        close(faces[0].normal_at().dot(faces[1].normal_at()),0)
        close(s.volume,strap_corner_volume(load(name).PARAMETERS),.001)
        return "Perpendicular planar contact faces with 27 mm usable length, 3 mm open corner relief, 6 mm rounded strap-bearing radius, 27 mm straight groove height, 2 mm projecting lips, supported upper ramp, flat bed lip, and independent integrated volume."
    if name == "tube_reducer":
        for z,inner,outer in ((11,25.2,27.6),(37,19.7,23.1),(62,16.2,18.6),
                              (.375,25.5,27.6),(71.625,16.5,18.6)):
            for radius,material in ((inner-.05,False),(inner+.05,True),
                                    (outer-.05,True),(outer+.05,False)):
                for angle in (0,pi/2,pi,3*pi/2):
                    contains(s,(radius*cos(angle),radius*sin(angle),z),material)
        contains(s,(15,0,51.95),True)
        contains(s,(15,0,52.05),False)
        for z in (.01,22,51.99,52.01,71.99):
            contains(s,(0,0,z),False)
        close(s.volume,reducer_volume(load(name).PARAMETERS),.001)
        return "50.4/32.4 mm socket bores, 22/20 mm straight sockets, 30 mm conical transition, 28.4 mm minimum flow bore, small-end annular stop, two 0.6 mm radial entry leads; continuous opening and independent cylinder/frustum volume."
    if name == "socket_fit_ring":
        for z,inner in ((.375,25.5),(4,25.2),(7.625,25.5)):
            for radius,material in ((inner-.05,False),(inner+.05,True),(27.55,True),(27.65,False)):
                contains(s,(radius,0,z),material)
            contains(s,(0,0,z),False)
        close(s.volume,socket_ring_volume(load(name).PARAMETERS),.001)
        return "50.4 mm working bore, 55.2 mm outside diameter, 8 mm height, two 0.6 mm entry leads, 6.5 mm straight bore, open both ends; independent analytic volume."
    if name == "ruler_stop":
        for y,material in ((2.95,True),(3.05,False),(6.15,False),(6.25,True)):
            contains(s,(0,y,12),material)
        for sign in (-1,1):
            for x,material in ((13.15,False),(13.25,True),(17.15,True),(17.25,False)):
                contains(s,(sign*x,4.5,12),material)
        for z in (.01,23.99):
            contains(s,(0,4.5,z),False)
        close(s.volume,(34.4*10.2-(4-pi)*1.5**2-26.4*3.2)*24,.01)
        return "26.4 x 3.2 mm open ruler/wedge passage, 3 mm lower floor, 4 mm roof and side walls, 24 mm reference length; analytic volume; prints end profile down."
    if name == "ruler_wedge":
        for point,material in [((.1,0,.75),True),((.1,0,.85),False),
                               ((17.5,0,1.85),True),((17.5,0,1.95),False),
                               ((30,0,2.65),True),((30,0,2.75),False),
                               ((33,0,6.95),True),((33,0,7.05),False),
                               ((31.9,0,4),False),((32.1,0,4),True),
                               ((20,11.95,1),True),((20,12.05,1),False)]:
            contains(s,point,material)
        close(s.volume,24*(35*(.8+3)/2+3*(7-(.8+2.2*32/35+3)/2)),.01)
        return "35 mm linear taper from 0.8 to 3 mm, 24 mm span, flat lower contact face, 3 mm-long raised pull grip reaching 7 mm total height; analytic volume."
    if name == "workshop_scoop":
        from build123d import Pos, RectangleRounded, extrude
        for point,material in [((0,0,2.35),True),((0,0,2.45),False),
                               ((-27.65,0,10),True),((-27.55,0,10),False),
                               ((29,0,15.9),True),((29,0,16.1),False),((29,12,19),True),
                               ((29,8,16.2),True),((29,8,16.35),False),
                               ((-50,0,3.9),True),((-50,0,4.1),False),
                               ((-71,1.7,2),False),((-71,2.3,2),True),((-29.5,0,3.9),True)]:
            contains(s,point,material)
        for sign in (-1,1):
            for y,material in ((20.05,False),(20.15,True),(22.45,True),(22.55,False)):
                contains(s,(0,sign*y,10),material)
        for radius,material in ((3.55,False),(3.65,True),(5.95,True),(6.05,False)):
            contains(s,(24+radius/sqrt(2),16.5+radius/sqrt(2),10),material)
        fill = Pos(0,0,2.4)*extrude(RectangleRounded(55.2,40.2,3.6),amount=13.6)
        overlap = s & fill
        close(0 if overlap is None else overlap.volume,0,1e-6)
        close(s.distance_to(fill),0,1e-6)
        expected_fill = (55.2*40.2-(4-pi)*3.6**2)*13.6
        close(fill.volume,expected_fill,.01)
        return f"2.4 mm floor/walls and preserved rounded-corner wall; 16 mm spill lip with rounded notch; continuous low handle and hanging hole; virtual fill seats without overlap, nominal capacity {expected_fill/1000:.6f} mL. Uncalibrated."
    if name == "plant_marker":
        for point,material in [((0,18,1.2),True),((0,38.75,1.2),False),
                               ((1.7,38.75,1.2),False),((1.8,38.75,1.2),True),
                               ((0,-70.05,1.2),False),((0,-69.95,1.2),True)]:
            contains(s,point,material)
        for sign in (-1,1):
            for x,y,material in ((3.95,-30,True),(4.05,-30,False),(2.25,-62.5,True),(2.35,-62.5,False),
                                  (.59,-69.95,True),(.65,-69.95,False),(4.2,-1,True),(4.35,-1,False)):
                contains(s,(sign*x,y,1.2),material)
        expected = (26*45-(4-pi)*3**2+8*55+(8+1.2)*15/2+2*(4-pi)-pi*1.75**2)*2.4
        close(s.volume,expected,.01)
        return "Blank rounded label, 8 mm stake, 15 mm taper to 1.2 mm flat tip, 2 mm neck blends, 3.5 mm hanging hole; one 2.4 mm extrusion on Z=0 and analytic volume."
    if name == "bookend":
        for point,material in [((40,0,3.99),True),((40,0,4.01),False),
                               ((96,0,2.55),True),((96,0,2.65),False),
                               ((99.9,0,1.2),True),((99.9,0,1.27),False),
                               ((-4.05,0,100),False),((-3.95,0,100),True),
                               ((-15,0,30),False)]:
            contains(s,point,material)
        for sign in (-1,1):
            for z,material in ((50.9,True),(51.05,False)):
                contains(s,(-15,sign*32,z),material)
            for y,z,material in ((17.6,63.85,False),(17.6,29.15,True),(17.6,29.25,False),
                                  (20.55,40,False),(20.65,40,True),
                                  (22.65,80,False),(22.8,80,True)):
                contains(s,(-2,sign*y,z),material)
            for z in (20,110):
                contains(s,(.05,sign*30,z),False)
        # Integrate the front bevel across the straight part and the two
        # rounded footprint corners, independently of the CAD subtraction.
        bevel_volume = 350+505.05+6.3+7.875*pi
        expected = ((130*80-(4-pi)*3**2)*4 + 4*80*126 + 2*(23*90/2*4)
                    - 2*(19.2*69.3/2*4) - bevel_volume)
        close(s.volume,expected,.01)
        return "Flat X=0 book face, 4 mm floor/wall, two rear braces, two pointed windows, 1.2 mm front tip and analytic volume including rounded-corner bevel integral. Stability/load untested."
    if name == "corner_cable_guide":
        from build123d import Align, Box, Pos, Torus
        for radius,z,material in ((30,2.35,True),(30,2.45,False),
                                  (22.55,6,False),(22.65,6,True),(24.95,6,True),(25.05,6,False),
                                  (34.95,6,False),(35.05,6,True),(37.35,6,True),(37.45,6,False)):
            contains(s,(radius/sqrt(2),radius/sqrt(2),z),material)
        for swap in (False,True):
            for y,material in ((24.9,True),(30,False),(35.1,True)):
                contains(s,(y,.01,6) if swap else (.01,y,6),material)
        for angle in (pi/6,pi/3):
            x,y = 41*cos(angle),41*sin(angle)
            contains(s,(x,y+1.7,1),False)
            contains(s,(x,y+1.8,1),True)
        cord = Pos(0,0,6.4)*Torus(30,4)
        cord &= Box(60,60,20,align=(Align.MIN,Align.MIN,Align.MIN))
        overlap = s & cord
        close(0 if overlap is None else overlap.volume,0,1e-6)
        close(s.distance_to(cord),0,1e-6)
        lifted = s & (Pos(0,0,2)*cord)
        close(0 if lifted is None else lifted.volume,0,1e-6)
        return "25/35 mm channel radii, 2.4 mm floor and walls, 8 mm clear depth, two open ports and 3.5 mm mounting holes; virtual 8 mm cable on 30 mm centerline radius seats and lifts without overlap."
    if name == "marking_saddle":
        from build123d import Align, Box, Pos
        for sign in (-1,1):
            for y,material in ((19.2,False),(19.3,True),(22.2,True),(22.3,False)):
                contains(s,(0,sign*y,10),material)
        contains(s,(0,0,2.99),True)
        contains(s,(0,0,3.01),False)
        for y in (-18,0,18):
            for offset,material in ((.45,False),(.55,True)):
                contains(s,(-27+offset,y,1),material)
                contains(s,(9+y+offset/sqrt(2),y-offset/sqrt(2),1),material)
        fences = [f for f in s.faces() if abs(abs(f.center().Y)-19.25) < 1e-6
                  and abs(f.normal_at().Y) > .999 and f.bounding_box().max.Z > 22.9]
        assert len(fences) == 2
        close(fences[0].distance_to(fences[1]),38.5)
        stock = Pos(0,0,3)*Box(100,38,25,align=(Align.CENTER,Align.CENTER,Align.MIN))
        overlap = s & stock
        close(0 if overlap is None else overlap.volume,0,1e-6)
        close(s.distance_to(stock),0,1e-6)
        expected = (90*44.5-(4-pi)*1.5**2)*23-90*38.5*20-3*38.5*(1+sqrt(2))
        close(s.volume,expected,.01)
        return "38.5 mm fence gap; virtual 38 mm board seats without overlap; 1 mm normal-width 90/45-degree slots; 3 mm plate, 20 mm fences; analytic volume."
    if name == "roll_adapter":
        from build123d import Circle, Pos, Rot, extrude
        for point,material in [((4.25,0,10),False),((4.35,0,10),True),
                               ((29.95,0,1),True),((30.05,0,1),False),
                               ((28,0,2.35),True),((28,0,2.45),False),
                               ((15,1.45,10),True),((15,1.55,10),False),
                               ((4.77,0,17.3),False),((4.87,0,17.3),True)]:
            contains(s,point,material)
        for radius,z,material in ((7.25,10,True),(7.35,10,False),(23.35,10,False),
                                  (23.45,10,True),(25.75,10,True),(25.85,10,False),
                                  (25.23,17.3,True),(25.33,17.3,False)):
            contains(s,(radius*cos(pi/6),radius*sin(pi/6),z),material)
        for angle in range(0,360,60):
            contains(s,(15*cos(radians(angle)),15*sin(radians(angle)),10),True)
            contains(s,(15*cos(radians(angle+30)),15*sin(radians(angle+30)),10),False)
        roll = Pos(0,0,2.4)*extrude(Circle(35)-Circle(26),amount=50)
        opposite = Pos(0,0,54.8)*Rot(0,180,0)*s
        rod = Pos(0,0,-2)*extrude(Circle(4),amount=60)
        for adapter in (s,opposite):
            overlap = adapter & roll
            close(0 if overlap is None else overlap.volume,0,1e-6)
            close(adapter.distance_to(roll),0,1e-6)
            close(adapter.distance_to(rod),.3,1e-6)
        close(s.distance_to(opposite),20,1e-6)
        return "51.6 mm sleeve, tapered tip, six 3 mm spokes and open sectors, 60 mm flange, 8.6 mm bore; two copies seat on a 50 mm virtual roll with 20 mm separation and no overlap; 8 mm rod clears by 0.3 mm radially."
    if name == "hand_knob":
        from build123d import Circle, Pos, RegularPolygon, extrude
        for point,material in [((0,0,7),False),((3.25,0,7),False),((3.35,0,7),True),
                               ((4,0,8.55),True),((4,0,8.65),False)]:
            contains(s,point,material)
        for sign in (-1,1):
            for y,z,material in ((5.1,10,False),(5.2,10,True),(5.4,13.9,False),(5.5,13.9,True)):
                contains(s,(0,sign*y,z),material)
        for angle in range(0,360,60):
            for radius,material in ((19.9,True),(20.1,False)):
                contains(s,(radius*cos(radians(angle)),radius*sin(radians(angle)),7),material)
        nut = Pos(0,0,8.6)*extrude(RegularPolygon(10/sqrt(3),6)-Circle(3),amount=5)
        overlap = s & nut
        close(0 if overlap is None else overlap.volume,0,1e-6)
        close(s.distance_to(nut),0,1e-6)
        close(14-nut.bounding_box().max.Z,.4)
        return "Six rounded lobes, 6.6 mm bore, 10.3 mm across-flat pocket with 8.6 mm floor and entry bevel; virtual 10 AF x 5 nut seats without overlap, 0.4 mm below top. Torque untested."
    if name == "slotted_shim":
        for point,material in [((19.9,3.25,1),False),((19.9,3.35,1),True),
                               ((-8.05,0,1),True),((-7.95,0,1),False),
                               ((-4.7,3.25,1),False),((-4.7,3.35,1),True),
                               ((-14,2.2,1),False),((-14,2.3,1),True),
                               ((0,8,1.99),True),((0,8,2.01),False)]:
            contains(s,point,material)
        slot_area = 6.6*(28-3.3)+pi*3.3**2/2
        expected = 2*(40*24-(4-pi)*3**2-slot_area-pi*2.25**2)
        close(s.volume,expected,.01)
        return "2 mm constant thickness, open 6.6 mm slot with 28 mm full depth and semicircular end, 12 mm closed back, 4.5 mm hanging hole; analytic volume."
    if name == "fold_clip":
        from build123d import Align, Box, Pos
        for point,material in [((-3.1,0,6),True),((-2.9,0,6),False),
                               ((-5.35,0,6),True),((-5.45,0,6),False),
                               ((39,0,6),False),((39,.4,6),True)]:
            contains(s,point,material)
        for sign in (-1,1):
            for y,material in ((1.55,False),(1.7,True),(4,True),(4.1,False)):
                contains(s,(20,sign*y,6),material)
        upper = s & (Pos(10,0,-1)*Box(40,10,14,align=(Align.MIN,Align.MIN,Align.MIN)))
        lower = s & (Pos(10,-10,-1)*Box(40,10,14,align=(Align.MIN,Align.MIN,Align.MIN)))
        throat = upper.distance_to(lower)
        assert .6 <= throat <= .65, "Rounded noses must preserve the intended small throat."
        return f"U root with 3 mm inner radius, tapered arms, open flared mouth; actual rounded throat {throat:.6f} mm. No flexure or force simulation."
    if name == "cord_clip":
        from build123d import Circle, Pos, extrude
        for point,material in [((0,6.3,6),False),((0,1,6),True),((0,9,6),False)]:
            contains(s,point,material)
        for sign in (-1,1):
            for x,y,material in ((3.25,6.3,False),(3.35,6.3,True),(4.35,6.3,False),
                                  (2.59,8.8,False),(2.61,8.8,True)):
                contains(s,(sign*x,y,6),material)
        cord = Pos(0,6.3,0)*extrude(Circle(3),amount=12)
        close(s.distance_to(cord),.3)
        overlap = s & cord
        close(0 if overlap is None else overlap.volume,0)
        assert (s & (Pos(0,2,0)*cord)).volume > 1, "The entry must require arm deflection."
        backs = [f for f in s.faces() if abs(f.center().Y) < 1e-6 and f.normal_at().Y < -.999]
        assert len(backs) == 1
        close(backs[0].area,216)
        return "6.6 mm cavity, 5.2 mm entry, seated 6 mm cord clears by 0.3 mm radially; insertion needs flex; 216 mm2 flat adhesive face. No deflection/retention simulation."
    if name == "round_stock_cradle":
        contains(s,(0,0,7.9),True)
        contains(s,(0,0,8.1),False)
        for diameter in (6,25,50):
            r = diameter/2
            for sign in (-1,1):
                y,z = sign*r/sqrt(2),8+r/sqrt(2)
                close(sqrt(y*y+(z-(8+sqrt(2)*r))**2),r)
                contains(s,(0,y+sign*.02/sqrt(2),z-.02/sqrt(2)),True)
                contains(s,(0,y-sign*.02/sqrt(2),z+.02/sqrt(2)),False)
        for x in (-30,30):
            for y in (-26,26):
                contains(s,(x,y,15),False)
                contains(s,(x+1.95,y,15),False)
                contains(s,(x+2.05,y,15),True)
        expected = (80*60-(4-pi)*3**2)*30-80*22**2-4*pi*2**2*30
        close(s.volume,expected,.01)
        return "90-degree V with 8 mm apex; two-sided tangency for 6/25/50 mm stock; four 4 mm holes and analytic volume."
    if name == "tie_anchor":
        contains(s,(0,0,.8),True)
        contains(s,(0,0,7.5),True)
        for swap in (False,True):
            for x,y,z,material in ((9,2.35,3.15,False),(9,2.45,3.15,True),
                                    (9,1.8,3.9,False),(9,1.8,4.0,True),
                                    (9,0,6.1,False),(9,0,6.3,True)):
                contains(s,(y,x,z) if swap else (x,y,z),material)
        for sign in (-1,1):
            contains(s,(sign*8,sign*8,4),False)
        passage = (4.8*1.6+4.8*3/2)*26
        crossing = 4.8**2*1.6+4.8**2*3/3
        expected = (26**2-(4-pi)*3**2-2*pi*1.75**2)*8.6-2*passage+crossing
        close(s.volume,expected,.01)
        return "Two crossed 4.8 × 1.6 minimum passages, peaked roofs, closed floor/top, diagonal mounting holes, analytic volume."
    if name == "workshop_funnel":
        for point,material in [((0,34.2,1),False),((0,34.3,1),True),
                               ((0,38.95,1),True),((0,39.05,1),False),
                               ((19.95,0,20),False),((20.05,0,20),True),
                               ((21.95,0,20),True),((22.05,0,20),False),
                               ((4.95,0,59),False),((5.05,0,59),True),
                               ((6.95,0,59),True),((7.05,0,59),False),
                               ((44,2.2,1),False),((44,2.3,1),True),
                               ((49.95,0,1),True),((50.05,0,1),False)]:
            contains(s,point,material)
        for z in (.1,20,39.9,40.1,59.9):
            contains(s,(0,0,z),False)
        return "70 mm mouth, continuous cone-to-spout passage, 10 mm spout bore/14 mm outside, 2 mm radial wall, external hanging hole."
    if name in ("sliding_box","sliding_fit_channel"):
        z = 27.7 if name == "sliding_box" else 11.7
        contains(s,(0,0,1),True)
        contains(s,(0,0,3),False)
        for sign in (-1,1):
            contains(s,(0,sign*35,z-.05),True)
            contains(s,(0,sign*35,z+.05),False)
            contains(s,(0,sign*36.51,z+1.3),False)
            contains(s,(0,sign*36.61,z+1.3),True)
            contains(s,(0,sign*35.39,z+3.3),False)
            contains(s,(0,sign*35.49,z+3.3),True)
        if name == "sliding_box":
            contains(s,(-59,0,29),False)
            contains(s,(59,0,29),True)
            contains(s,(-59,0,27.6),True)
        else:
            contains(s,(-14.9,0,3),False)
            contains(s,(14.9,0,3),False)
        return "Closed floor, bottom support ledges, both sloped guide faces and retaining lips; correct entry/end geometry."
    if name in ("sliding_lid","sliding_fit_slider"):
        length = 123.2 if name == "sliding_lid" else 36
        for sign in (-1,1):
            contains(s,(0,sign*36.29,1.2),True)
            contains(s,(0,sign*36.39,1.2),False)
        contains(s,(length/2-.05,0,.1),False)
        contains(s,(length/2-.05,0,.7),True)
        contains(s,(-length/2+3,0,5.3),True)
        contains(s,(0,0,2.5),False)
        return "Matching 0.8-slope side profile, rear entry chamfer, flat sliding bottom, raised front pull grip."
    if name == "parts_tray":
        cell_x, cell_y = (150 - 4 * 2.4) / 3, (100 - 3 * 2.4) / 2
        for x in (-49.2, 0, 49.2):
            for y in (-24.4, 24.4):
                contains(s, (x, y, 1), True)
                contains(s, (x, y, 3), False)
        contains(s, (0, 0, 20), True)
        contains(s, (74, 0, 20), True)
        expected = (150 * 100 - (4-pi) * 4.4**2) * 24
        expected -= 6 * (cell_x * cell_y - (4-pi) * 2**2) * 22
        close(s.volume, expected, .001)
        return "Six open pockets, closed 2 mm floor, center divider, outer wall, analytic volume."
    if name == "cable_comb":
        cursor = -59 / 2 + 5
        slot_area = 0
        for width in (3.6, 4.6, 5.6, 6.6, 8.6):
            x = cursor + width / 2
            contains(s, (x, 8, 2), False)
            contains(s, (x - width / 2 + .05, 8, 2), False)
            contains(s, (x - width / 2 - .05, 8, 2), True)
            cursor += width + 5
            slot_area += width * (18 - width/2) + pi * width**2 / 8
        contains(s, (0, -9, 2), True)
        for x in (-24.5, 24.5):
            contains(s, (x, -9, 2), False)
        close(s.volume, (59*32-(4-pi)*4-slot_area-2*pi*2.25**2)*4, .001)
        return "All five slot widths, solid rear strip, two mounting holes, analytic volume."
    if name == "divider_foot":
        contains(s, (0, 0, 1), True)
        contains(s, (0, 0, 10), False)
        for sign in (-1, 1):
            contains(s, (sign * 1.65, 0, 10), False)
            contains(s, (sign * 1.75, 0, 10), True)
            contains(s, (sign * 1.75, 0, 19.7), False)
        close(s.volume, (34*24-(4-pi)*9)*2.4 + 2*3*24*(20-2.4)-24, .001)
        return "3.4 mm parallel slot, widened top entry, connected floor, analytic volume."
    if name == "divider_fit_coupon":
        cursor = -13 + 2.4
        for width in (3.2, 3.4, 3.6, 3.8):
            x = cursor + width/2
            contains(s, (x, 0, 1), True)
            contains(s, (x + width/2 - .05, 0, 5), False)
            contains(s, (x + width/2 + .05, 0, 5), True)
            contains(s, (x, -9.95, 5), False)
            contains(s, (x, 9.95, 5), False)
            cursor += width + 2.4
        return "All four clearance widths, both open ends for a full-length board, and closed floor."
    if name == "phone_stand":
        for point, material in [((40, 3, 30), True), ((10, 13, 30), True),
                                ((10, 16, 30), False), ((2, 20, 30), True),
                                ((50, 40, 30), False)]:
            contains(s, point, material)
        return "Base, phone seat, retaining lip, clear phone gap, and open triangular frame."
    if name == "corner_square":
        for point, material in [((40, 17.95, 4), True), ((40, 18.05, 4), False),
                                ((17.95, 40, 4), True), ((18.05, 40, 4), False),
                                ((18, 18, 4), False), ((9, 71, 4), False)]:
            contains(s, point, material)
        close(s.volume, (2*80*18-18**2-2*2**2-.75*pi*3**2-pi*2.5**2)*8, .001)
        return "Perpendicular inside datums, glue relief, hanging hole, analytic volume."
    if name == "handle_marking_jig":
        for x in (-64, 0, 64):
            contains(s, (x, 28, 2), False)
            contains(s, (x + 1.55, 28, 2), False)
            contains(s, (x + 1.65, 28, 2), True)
        contains(s, (0, 2.95, 10), True)
        contains(s, (0, 3.05, 10), False)
        contains(s, (0, 39.8, 2), False)
        return "128 mm outer hole pitch, 25 mm hole setback from fence, 3.2 mm holes, center notch."
    if name == "tube_squeezer":
        for z in (0.1, 5.9):
            contains(s, (0, 1.45, z), False)
            contains(s, (0, 1.55, z), True)
        contains(s, (0, .95, 3), False)
        contains(s, (0, 1.05, 3), True)
        contains(s, (31.95, 0, 3), False)
        contains(s, (32.05, 0, 3), True)
        body_area = 90*26-(4-pi)*8**2
        slot_area = (64-2)*2+pi
        perimeter = 2*(64-2)+pi*2
        bevels = (perimeter*.6**2 + 2*pi*.6**3/3)/.8
        close(s.volume, body_area*6-slot_area*6-bevels, .01)
        return "64 × 2 mm throat, both 38.7-degree lead-ins, positive end webs, analytic volume."
    if name == "soap_dish_tray":
        contains(s, (0, 0, 1.2), True)
        contains(s, (0, 0, 2.5), False)
        contains(s, (59, 0, 12), True)
        contains(s, (0, 41, 12), False)
        contains(s, (0, 41, 8), True)
        expected = (120*84-(4-pi)*6**2)*14
        expected -= (115.2*79.2-(4-pi)*3.6**2)*(14-2.4)
        expected -= 12*2.4*4
        close(s.volume, expected, .01)
        return "Closed 2.4 mm floor, open cavity, intact walls, lowered pour lip, analytic volume."
    if name == "soap_dish_insert":
        for x in range(-40, 41, 8):
            contains(s, (x, 0, 1.5), False)
        for x in (-49.6, 49.6):
            for y in (-31.6, 31.6):
                contains(s, (x, y, 1.5), True)
                contains(s, (x, y, 10.9), True)
        contains(s, (0, 36, 1.5), False)
        contains(s, (4, 0, 1.5), True)
        return "Eleven open drain slots, continuous webs, four connected feet, front lift notch."
    if name == "label_stand":
        contains(s, (0, 0, 3), True)
        contains(s, (0, 0, 8), False)
        for x in (-24.99, 24.99):
            contains(s, (x, 0, 8), False)
        gap_y = .8/cos(radians(12))
        contains(s, (0, gap_y/2-.01, 8), False)
        contains(s, (0, gap_y/2+.01, 8), True)
        slot_faces = [f for f in s.faces() if abs(abs(f.normal_at().Z)-sin(radians(12))) < 1e-6
                      and abs(abs(f.normal_at().Y)-cos(radians(12))) < 1e-6]
        assert len(slot_faces) == 2
        close(slot_faces[0].distance_to(slot_faces[1]), .8)
        close(s.volume, (50*24-(4-pi)*4**2)*12-gap_y*8*50, .001)
        return "0.8 mm normal slot width, 12 degree lean, 4 mm floor, both open ends, analytic volume."
    if name == "paint_pyramid":
        contains(s, (24, 0, 1), True)
        contains(s, (23, 0, 3), False)
        contains(s, (0, 0, 25.9), True)
        top_faces = [f for f in s.faces() if abs(f.bounding_box().min.Z-26) < 1e-6]
        assert len(top_faces) == 1
        close(top_faces[0].area, 2.4**2)
        close(s.volume, (50**2-(4-pi)*3**2)*2 + 24/3*(44**2+44*2.4+2.4**2), .001)
        return "Broad connected foot, 2.4 × 2.4 flat contact tip, analytic frustum volume."
    if name == "cable_winder":
        for point, material in [((0, 8, 2), True), ((0, 12, 2), False), ((0, 0, 2), False),
                                ((40.5, 0, 2), True), ((-40.5, 0, 2), True),
                                ((40.5, 20, 2), False), ((-40.5, -20, 2), False),
                                ((42.25, 20, 2), False), ((42.35, 20, 2), True)]:
            contains(s, point, material)
        return "Connected winding waist, both end caps, opposing 3.6 mm parking notches, center tie slot."
    if name == "hex_bit_rack":
        for x in (-30, -18, -6, 6, 18, 30):
            for y in (-12, 0, 12):
                contains(s, (x, y, 1.2), True)
                contains(s, (x, y, 6), False)
                contains(s, (x, y+3.3, 6), False)
                contains(s, (x, y+3.4, 6), True)
        a0, a1 = sqrt(3)/2*6.7**2, sqrt(3)/2*7.9**2
        extra_entry = .6*(a0+sqrt(a0*a1)+a1)/3 - .6*a0
        close(s.volume, (80*44-(4-pi)*3**2)*14-18*(a0*(14-2.4)+extra_entry), .01)
        return "All eighteen blind sockets, 6.7 mm across flats, 2.4 mm floors, analytic volume including entry bevels."
    if name == "hex_bit_fit_coupon":
        for x, af in ((-12,6.5), (0,6.7), (12,6.9)):
            contains(s, (x,0,1.2), True)
            contains(s, (x,0,3), False)
            contains(s, (x,af/2-.025,7), False)
            contains(s, (x,af/2+.025,7), True)
        return "6.5 / 6.7 / 6.9 mm across-flat sockets, intact 2.4 mm floors, matching rack insertion depth."
    if name == "sanding_block":
        for x in (-40,40):
            contains(s,(x,0,10.9),True)
            contains(s,(x,0,11.1),False)
            contains(s,(x,19.9,15),False)
            contains(s,(x,20.1,15),True)
            contains(s,(x+2.95,0,15),False)
            contains(s,(x+3.05,0,15),True)
        for point, material in [((0,0,16.9),True),((0,0,17.1),False),
                                ((49.4,0,.5),True),((49.8,0,.5),False),
                                ((46.9,0,24),True),((47.1,0,24),False)]:
            contains(s,point,material)
        expected = (100*25-1-16)*50 - 2*(6*40-(4-pi)*1.5**2)*14
        expected -= (64*34-(4-pi)*4**2)*8
        close(s.volume,expected,.01)
        return "Two 6 × 40 × 14 blind slots, 11 mm slot floors, grip recess, wrap-edge chamfers, analytic volume."
    if name == "sanding_wedge":
        contains(s,(0,0,.1),True)
        contains(s,(2.75,0,10),True)
        contains(s,(2.85,0,10),False)
        close(s.volume,36*20*(3.2+8)/2,.001)
        return "3.2-to-8 mm symmetric taper, 36 mm span, 20 mm height, analytic volume."
    if name == "cable_grommet":
        for point, material in [((-29.75,0,10),True),((-29.85,0,10),False),
                                ((-27.75,0,10),False),((-27.85,0,10),True),
                                ((28,4.9,10),False),((28,5.1,10),True),
                                ((0,33,1),True),((0,34.1,1),False),
                                ((0,28.27,.1),False),((0,28.37,.1),True),
                                ((-29.23,0,18.3),True),((-29.33,0,18.3),False)]:
            contains(s,point,material)
        return "59.6 mm sleeve OD, 55.6 mm bore, 68 mm flange, open 10 mm cable entry, flange lead-in, tapered sleeve tip."
    if name == "radius_template":
        for r,(sx,sy) in zip((5,10,15,20),((-1,-1),(1,-1),(1,1),(-1,1))):
            for delta,material in ((-.05,True),(.05,False)):
                contains(s,(sx*(40-r+(r+delta)/sqrt(2)),
                            sy*(40-r+(r+delta)/sqrt(2)),1),material)
        contains(s,(0,9.95,1),False)
        contains(s,(0,10.05,1),True)
        expected = (80**2-(1-pi/4)*sum(r*r for r in (5,10,15,20))-pi*10**2)*3
        close(s.volume,expected-10*.8*3*.6,.01)
        return "Four actual corner arcs R5/R10/R15/R20, 20 mm finger hole, ten recessed ticks, analytic volume."
    if name == "center_finder":
        contains(s,(0,0,2),False)
        contains(s,(1.55,0,2),False)
        contains(s,(1.65,0,2),True)
        contains(s,(0,2.25,.1),False)
        contains(s,(0,2.35,.1),True)
        for width in (20,45,72):
            nx = (width+8)/80
            ny = sqrt(1-nx*nx)
            contacts = []
            for sign in (-1,1):
                x,y = sign*40-sign*4*nx,-sign*4*ny
                close(x*nx+y*ny,sign*width/2)
                contains(s,(x+sign*.02*nx,y+sign*.02*ny,6),True)
                contains(s,(x-sign*.02*nx,y-sign*.02*ny,6),False)
                contacts.append((x,y))
            close(np.mean(contacts,axis=0),(0,0))
        base = ((100-24)*24+pi*12**2)*4-pi*1.6**2*4
        entry = pi*((2.4**2+2.4*1.6+1.6**2)/3-1.6**2)
        tip_reduction = pi*.75*(4**2-(4**2+4*3.4+3.4**2)/3)
        close(s.volume,base-entry+2*(pi*4**2*12-tip_reduction),.01)
        return "Equal 8 mm pins, midpoint 3.2 mm hole; tangency and centered marking at stock widths 20/45/72 mm; analytic volume."
    if name == "brush_rest":
        for y in (-45,-5):
            for x,r in ((-30,4.3),(0,6.3),(30,8.3)):
                edge = sqrt(r*r-.1**2)
                contains(s,(x+edge-.05,y,19.9),False)
                contains(s,(x+edge+.05,y,19.9),True)
                contains(s,(x,y,20-r+.05),False)
                contains(s,(x,y,20-r-.05),True)
                contains(s,(x,y,1.2),True)
                contains(s,(x,y,6),False)
                contains(s,(x+3,y,6),True)
        contains(s,(0,40,1.2),True)
        contains(s,(0,40,3),False)
        contains(s,(0,74,10),False)
        contains(s,(0,74,8),True)
        return "Six matching 8.6/12.6/16.6 mm cradles, intact floor, six wash portals and their roofs, open catch region, lowered pouring lip."
    if name == "utility_peg":
        for x in (-22,22):
            contains(s,(x,0,1.5),False)
            contains(s,(x+2.15,0,1.5),False)
            contains(s,(x+2.25,0,1.5),True)
        for point,material in [((6.8,0,3.1),True),((7.1,0,3.1),False),
                               ((4.95,0,15),True),((5.05,0,15),False),
                               ((5.85,0,26),True),((6,0,26),False),
                               ((7.95,0,30),True),((8.05,0,30),False)]:
            contains(s,point,material)
        base = (60*24-(4-pi)*4**2-2*pi*2.2**2)*3
        stem = pi*5**2*21.85
        collar_extra = pi*(7**2+7*5+5**2)-pi*5**2*3
        head = pi*3.75/3*(5**2+5*8+8**2)+pi*8**2*2.4
        close(s.volume,base+stem+collar_extra+head,.01)
        return "Two 4.4 mm mounting holes on 44 centers, 10 mm stem, broad root, tapered 16 mm retaining head, analytic volume."


def divider_joint_volume(p):
    gap = p['board_thickness']+p['clearance']
    hub = gap+2*p['wall']
    radius = min(.6,p['wall']/4)
    # Each arm fills its two neighboring hub corners. The other corners retain
    # their quarter-circle rounding; both outside mouth corners remain rounded.
    corners = ((0,90),(90,180),(180,270),(270,0))
    retained = sum(not any(angle in p['ports'] for angle in pair) for pair in corners)
    area = hub*hub+len(p['ports'])*p['insertion_depth']*hub
    area -= (2*len(p['ports'])+retained)*(1-pi/4)*radius*radius
    removed = p['insertion_depth']*(gap*(p['height']-p['floor'])+p['lead_in']**2/.8)
    return area*p['height']-len(p['ports'])*removed


def divider_joint_features(shape,p):
    from divider_joint_common import dimensions,settings
    p = settings(p)
    s = sound(shape)
    gap,hub,end = dimensions(p)
    close(s.volume,divider_joint_volume(p),.001)
    for z in (.1,p['floor']+.1,p['height']-.1):
        contains(s,(0,0,z),True)
    for angle in (0,90,180,270):
        theta = radians(angle)
        def point(x,y,z):
            return (x*cos(theta)-y*sin(theta),x*sin(theta)+y*cos(theta),z)
        middle = (p['floor']+p['height']-p['lead_in']/.8)/2
        if angle not in p['ports']:
            contains(s,point(hub/2+1,0,middle),False)
            continue
        for x in (hub/2+.1,hub/2+p['insertion_depth']/2,end-.8):
            contains(s,point(x,0,p['floor']-.05),True)
            contains(s,point(x,0,p['floor']+.05),False)
            for side in (-1,1):
                contains(s,point(x,side*(gap/2-.05),middle),False)
                contains(s,point(x,side*(gap/2+.05),middle),True)
        contains(s,point(hub/2-.05,0,middle),True)
        contains(s,point(hub/2+.05,0,middle),False)
        contains(s,point(end+.05,0,p['floor']/2),False)
        top_mid = p['height']-p['lead_in']/.8/2
        for side in (-1,1):
            for offset,material in ((-.05,False),(.05,True)):
                contains(s,point(hub/2+2,side*(gap/2+p['lead_in']/2+offset),top_mid),material)
    for invalid in ({'ports':(0,)},{'ports':(0,45)},{'ports':(0,0)},
                    {'wall':2,'lead_in':.8},{'height':12,'floor':4.1}):
        try:
            settings(p | invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Divider joint accepted {invalid}")
    return dict(port_angles_degrees=p['ports'],slot_width_mm=gap,
                hub_width_mm=hub,insertion_depth_mm=p['insertion_depth'],
                board_floor_height_mm=p['floor'],top_lead_slope=.8,
                all_slots_and_leads_probed=True,analytic_volume_mm3=divider_joint_volume(p))


def divider_assembly_checks():
    from build123d import Align,Box,Pos,Rot
    from divider_joint_common import dimensions,settings
    module = load('divider_joint_assembly')
    results = []
    for label,overrides,length,height,bounds in (
            ('cross',{},80,50,(168.2,168.2,52.4)),
            ('T',DIVIDER_T,60,35,(126.3,66.3,37)),
            ('corner',DIVIDER_CORNER,100,70,(112.8,112.8,73))):
        p = settings(overrides)
        assembly = module.build(reference_length=length,reference_height=height,**p)
        assert assembly.is_valid and len(assembly.solids()) == 1+len(p['ports'])
        close(tuple(assembly.bounding_box().size),bounds)
        connector,*boards = assembly.children
        close(connector.volume,divider_joint_volume(p),.001)
        for i,left in enumerate(assembly.children):
            for right in assembly.children[i+1:]:
                overlap = left & right
                close(0 if overlap is None else overlap.volume,0,1e-6)
        gap,hub,end = dimensions(p)
        for angle,board in zip(p['ports'],boards):
            theta = radians(angle)
            close(board.volume,length*p['board_thickness']*height,.001)
            close(board.bounding_box().min.Z,p['floor'])
            close(board.distance_to(connector),0,1e-6)
            # Small virtual contact patches isolate the end stop and floor.
            end_patch = Rot(0,0,angle)*Pos(hub/2,0,p['floor']+2)*Box(
                .1,p['board_thickness']/2,2,align=(Align.MIN,Align.CENTER,Align.MIN))
            floor_patch = Rot(0,0,angle)*Pos(hub/2+2,0,p['floor'])*Box(
                2,p['board_thickness']/2,.1,align=(Align.MIN,Align.CENTER,Align.MIN))
            close(end_patch.distance_to(connector),0,1e-6)
            close(floor_patch.distance_to(connector),0,1e-6)
            outward = Pos(.5*cos(theta),.5*sin(theta),0)
            close((outward*end_patch).distance_to(connector),.5,1e-6)
            overlap = connector & (outward*board)
            close(0 if overlap is None else overlap.volume,0,1e-6)
            for movement in (Pos(-.1*cos(theta),-.1*sin(theta),0),Pos(0,0,-.1)):
                overlap = connector & (movement*board)
                assert overlap is not None and overlap.volume > .01
            # Probe each side gap, away from the floor and entry lead.
            for side in (-1,1):
                patch = Rot(0,0,angle)*Pos(hub/2+2,side*p['board_thickness']/2,p['floor']+2)*Box(
                    2,.01,2,align=(Align.MIN,Align.CENTER,Align.MIN))
                close(patch.distance_to(connector),p['clearance']/2-.005,1e-6)
        results.append(dict(case=label,overrides=overrides,reference_length_mm=length,
                            reference_height_mm=height,component_count=1+len(boards),
                            pairwise_overlap_mm3=0,all_boards_contact_floor_and_backstop=True,
                            side_gap_mm=p['clearance']/2,withdrawal_gap_mm=.5,
                            over_insertion_and_lowering_obstructed=True,
                            board_cut_length_for_180mm_centers_mm=180-hub))
    print('PASS divider joint: cross, T, corner; board gaps, contacts, withdrawal, interference',flush=True)
    return results


def sieve_volume(p,count):
    outer = p['bowl_diameter']/2
    inner = outer-p['wall']
    root_x = -outer+2*p['wall']
    half = p['handle_width']/2
    # Area of a circle left of the handle's root plane and within its width.
    # This integrates the circular intersection independently of CAD booleans.
    def intersection_area(radius):
        b = min(half,sqrt(radius*radius-root_x*root_x))
        return 2*b*root_x+b*sqrt(radius*radius-b*b)+radius*radius*asin(b/radius)
    handle_area = (p['handle_length']+2*p['wall']-half)*2*half+pi*half*half/2
    bowl = pi*(outer*outer*p['height']-inner*inner*(p['height']-p['floor']))
    handle = ((handle_area-intersection_area(outer))*p['handle_thickness']
              +intersection_area(inner)*(p['handle_thickness']-p['floor']))
    holes = count*pi*(p['hole_diameter']/2)**2*p['floor']
    hanger = pi*(p['hanging_hole']/2)**2*p['handle_thickness']
    return bowl+handle-holes-hanger


def sieve_features(shape,p,expected_count):
    from build123d import GeomType,Pos,Sphere
    s = shape.solids()[0]
    diameter,floor,pitch = (p[key] for key in ('hole_diameter','floor','pitch'))
    # Discover the actual full-depth cylindrical openings in the solid.
    bores = [f for f in s.faces() if f.geom_type==GeomType.CYLINDER
             and abs(f.radius-diameter/2)<1e-6 and abs(f.bounding_box().size.Z-floor)<1e-6
             and abs(f.bounding_box().size.X-diameter)<1e-6
             and abs(f.bounding_box().size.Y-diameter)<1e-6]
    assert len(bores)==expected_count
    centers = [tuple(f.bounding_box().center())[:2] for f in bores]
    inner = p['bowl_diameter']/2-p['wall']
    margins = []
    for x,y in centers:
        row = round(y/(pitch*sqrt(3)/2))
        close(y,row*pitch*sqrt(3)/2)
        column = x/pitch-(row%2)/2
        close(column,round(column))
        margin = inner-sqrt(x*x+y*y)-diameter/2
        assert margin >= p['hole_margin']-1e-6
        margins.append(margin)
        for z in (.05,floor/2,floor-.05):
            contains(s,(x,y,z),False)
        for angle in (0,pi/2,pi,3*pi/2):
            for radius,material in ((diameter/2-.04,False),(diameter/2+.04,True)):
                contains(s,(x+radius*cos(angle),y+radius*sin(angle),floor/2),material)
    neighbor_distances = []
    for index,(x,y) in enumerate(centers):
        for u,v in centers[index+1:]:
            distance = sqrt((x-u)**2+(y-v)**2)
            neighbor_distances.append(distance)
            if abs(distance-pitch)<1e-6:
                contains(s,((x+u)/2,(y+v)/2,floor-.05),True)
                contains(s,((x+u)/2,(y+v)/2,floor+.05),False)
    close(min(neighbor_distances),pitch)
    for angle in (0,pi/2,pi,3*pi/2):
        for radius,material in ((inner-.05,False),(inner+.05,True)):
            contains(s,(radius*cos(angle),radius*sin(angle),p['height']-.2),material)
    low = -p['bowl_diameter']/2-p['handle_length']
    hanger_x = low+p['handle_width']/2
    contains(s,(hanger_x,0,p['handle_thickness']/2),False)
    contains(s,(hanger_x,p['hanging_hole']/2+.1,p['handle_thickness']/2),True)
    contains(s,(-p['bowl_diameter']/2-.05,0,p['handle_thickness']-.05),True)
    contains(s,(-p['bowl_diameter']/2+.05,0,p['handle_thickness']-.05),True)
    close(s.volume,sieve_volume(p,expected_count),.002)
    samples = [min(centers,key=lambda c:c[0]**2+c[1]**2),min(centers),max(centers)]
    passing = (diameter-.2)/2
    stopped = (diameter+.2)/2
    contact_z = floor+sqrt(stopped*stopped-(diameter/2)**2)
    for x,y in samples:
        for z in (-passing-.2,floor/2,floor+passing+.2):
            ball = Pos(x,y,z)*Sphere(passing)
            overlap = s & ball
            close(0 if overlap is None else overlap.volume,0,1e-6)
        ball = Pos(x,y,contact_z)*Sphere(stopped)
        overlap = s & ball
        close(0 if overlap is None else overlap.volume,0,1e-6)
        close(s.distance_to(ball),0,1e-6)
        pushed = s & (Pos(0,0,-.2)*ball)
        assert pushed is not None and pushed.volume>.001
    aperture_area = expected_count*pi*(diameter/2)**2
    return dict(hole_count=expected_count,aperture_diameter_mm=diameter,floor_thickness_mm=floor,
                triangular_pitch_mm=pitch,minimum_web_mm=min(neighbor_distances)-diameter,
                minimum_actual_wall_margin_mm=min(margins),opening_area_mm2=aperture_area,
                percent_of_circular_floor_open=100*aperture_area/(pi*inner**2),
                smaller_sphere_passes_mm=diameter-.2,larger_sphere_stops_mm=diameter+.2,
                sphere_test_positions=len(samples),analytic_volume_mm3=sieve_volume(p,expected_count))


def aperture_coupon_features(shape,p):
    s = shape.solids()[0]
    diameters = [p['hole_diameter']+value for value in p['offsets']]
    pitch = max(12,max(diameters)+4)
    length = (len(diameters)-1)*pitch+pitch+4
    depth = max(18,max(diameters)+9)
    close(tuple(s.bounding_box().size),(length,depth,p['floor']))
    for index,diameter in enumerate(diameters):
        x = (index-(len(diameters)-1)/2)*pitch
        for z in (.05,p['floor']/2,p['floor']-.05):
            contains(s,(x,0,z),False)
        for radius,material in ((diameter/2-.04,False),(diameter/2+.04,True)):
            contains(s,(x+radius,0,p['floor']/2),material)
        for tick in range(index+1):
            tx = x+(tick-index/2)*1.6
            contains(s,(tx,depth/2-2,p['floor']-.2),False)
            contains(s,(tx,depth/2-2,p['floor']-.45),True)
        contains(s,(x+(index+1-index/2)*1.6,depth/2-2,p['floor']-.2),True)
    expected = ((length*depth-(4-pi)*3**2-sum(pi*(d/2)**2 for d in diameters))*p['floor']
                -sum(range(1,len(diameters)+1))*.7*1.6*.4)
    close(s.volume,expected,.001)
    return dict(aperture_diameters_mm=diameters,floor_thickness_mm=p['floor'],
                identifying_tick_counts=list(range(1,len(diameters)+1)),recess_depth_mm=.4,
                open_both_ends=True,analytic_volume_mm3=expected)


def strap_corner_volume(p):
    length,wall,relief,lip = (p[key] for key in ('leg_length','wall','corner_relief','lip_projection'))
    area = lambda t: 2*length*t+pi*t*t/4-3*pi*relief*relief/4
    ramp_height = lip/.8
    total_height = 2*p['lip_thickness']+p['strap_width']+p['width_clearance']+ramp_height
    # Integrate the added lip area through its linear increase in radius.
    ramp_extra = ramp_height*(length*lip+pi/4*(wall*lip+lip*lip/3))
    return (area(wall)*total_height+2*p['lip_thickness']*(area(wall+lip)-area(wall))+ramp_extra)


def strap_assembly_checks():
    from build123d import GeomType,Pos
    from strap_corner_common import settings,height
    module = load('strap_clamp_assembly')
    results = []
    for label,overrides,frame_dims in (("default",{},(180,130,30,20)),
                                        ("compact",STRAP_COMPACT,(120,80,18,14)),
                                        ("large",STRAP_LARGE,(260,190,48,30))):
        p = settings(overrides)
        width,depth,frame_height,rail = frame_dims
        assembly = module.build(frame_width=width,frame_depth=depth,frame_height=frame_height,
                                rail_width=rail,**p)
        assert assembly.is_valid and len(assembly.solids()) == 6
        pads,frame,strap = assembly.children[:4],assembly.children[4],assembly.children[5]
        radius = p['wall']+p['lip_projection']
        close(tuple(assembly.bounding_box().size),(width+2*radius,depth+2*radius,max(frame_height,height(p))))
        for i,left in enumerate(assembly.children):
            for right in assembly.children[i+1:]:
                overlap = left & right
                close(0 if overlap is None else overlap.volume,0,1e-6)
        expected_face_area = (p['leg_length']-p['corner_relief'])*height(p)
        for pad in pads:
            close(pad.volume,strap_corner_volume(p),.001)
            faces = [f for f in pad.faces() if f.geom_type==GeomType.PLANE and abs(f.area-expected_face_area)<1e-5]
            assert len(faces) == 2
            close(faces[0].normal_at().dot(faces[1].normal_at()),0,1e-6)
            for face in faces:
                close(face.distance_to(frame),0,1e-6)
            close(pad.distance_to(strap),0,1e-6)
        root = pads[0]
        bottom_lip = [f for f in root.faces() if abs(f.center().Z-p['lip_thickness'])<1e-6 and f.normal_at().Z>.999]
        upper_lip = [f for f in root.faces() if f.bounding_box().min.Z>p['lip_thickness']+.1 and f.normal_at().Z<-.1]
        assert bottom_lip and upper_lip
        lower_gap = min(f.distance_to(strap) for f in bottom_lip)
        upper_gap = min(f.distance_to(strap) for f in upper_lip)
        close((lower_gap,upper_gap),(p['width_clearance']/2,p['width_clearance']/2),1e-5)
        lip_collisions = {}
        for direction,shift in (('up',p['width_clearance']/2+1),('down',-p['width_clearance']/2-.5)):
            moved = Pos(0,0,shift)*strap
            volumes = []
            for pad in pads:
                overlap = pad & moved
                volume = 0 if overlap is None else overlap.volume
                assert volume > .01, "The guide lip should obstruct this vertical movement."
                volumes.append(volume)
            lip_collisions[direction] = volumes
        close(frame.volume,(width*depth-(width-2*rail)*(depth-2*rail))*frame_height,.001)
        centerline_length = 2*(width+depth)+2*pi*(p['wall']+p['strap_thickness']/2)
        close(strap.volume,centerline_length*p['strap_thickness']*p['strap_width'],.001)
        close(strap.bounding_box().min.Z,p['lip_thickness']+p['width_clearance']/2)
        close(strap.bounding_box().size.Z,p['strap_width'])
        close(frame.distance_to(strap),p['wall'],1e-5)
        results.append(dict(case=label,overrides=overrides,reference_frame_dimensions_mm=frame_dims,
                            component_count=6,pairwise_overlap_mm3=0,perpendicular_contact_faces=8,
                            all_pads_contact_frame_and_strap=True,usable_contact_length_mm=p['leg_length']-p['corner_relief'],
                            lower_lip_gap_mm=lower_gap,upper_lip_gap_mm=upper_gap,
                            lip_extension_beyond_strap_mm=p['lip_projection']-p['strap_thickness'],
                            vertical_shift_overlap_mm3=lip_collisions,
                            reference_strap_centerline_length_mm=centerline_length,
                            analytic_pad_volume_mm3=strap_corner_volume(p)))
    print("PASS strap clamp: three sizes; eight perpendicular contacts, strap path, guide gaps, lips, no overlap",flush=True)
    return results


def socket_ring_volume(p):
    radius = (p['tube_diameter']+p['clearance'])/2
    entry_height = p['lead_in']/.8
    removed = 2*pi*entry_height*(radius*p['lead_in']+p['lead_in']**2/3)
    return pi*((radius+p['wall'])**2-radius**2)*p['height']-removed


def reducer_volume(p):
    # Independent sum of cylinders and conical frusta, less two entry leads.
    large = (p['large_diameter']+p['large_clearance'])/2
    small = (p['small_diameter']+p['small_clearance'])/2
    throat = small-p['stop_inset']
    outer_l,outer_s = large+p['wall'],small+p['wall']
    frustum = lambda a,b: pi*p['transition_length']*(a*a+a*b+b*b)/3
    outer = pi*(outer_l**2*p['large_depth']+outer_s**2*p['small_depth'])+frustum(outer_l,outer_s)
    inner = pi*(large**2*p['large_depth']+small**2*p['small_depth'])+frustum(large,throat)
    leads = pi*(p['lead_in']/.8)*((large+small)*p['lead_in']+2*p['lead_in']**2/3)
    return outer-inner-leads


def reducer_fit_checks():
    from build123d import Circle,Pos,extrude
    module,ring_module = load('tube_reducer'),load('socket_fit_ring')
    results = []
    for label,overrides in (("default",{}),("compact",REDUCER_COMPACT),("large",REDUCER_LARGE)):
        p = module.PARAMETERS | overrides
        body = module.build(**p)
        sound(body)
        close(body.volume,reducer_volume(p),.001)
        large = (p['large_diameter']+p['large_clearance'])/2
        small = (p['small_diameter']+p['small_clearance'])/2
        throat = small-p['stop_inset']
        slope = (large-throat)/p['transition_length']
        shoulder = p['large_depth']+p['transition_length']
        height = shoulder+p['small_depth']
        large_seat = p['large_depth']+p['large_clearance']/2/slope
        # Reference tubes have wall thickness equal to the chosen stop inset.
        # No tube standard or pressure rating is implied by these test fixtures.
        tube_wall = p['stop_inset']
        large_tube = Pos(0,0,-15)*extrude(
            Circle(p['large_diameter']/2)-Circle(p['large_diameter']/2-tube_wall),
            amount=large_seat+15)
        small_tube = Pos(0,0,shoulder)*extrude(
            Circle(p['small_diameter']/2)-Circle(p['small_diameter']/2-tube_wall),
            amount=p['small_depth']+15)
        overinserted,withdrawn = {},{}
        for end,tube,sign in (('large',large_tube,1),('small',small_tube,-1)):
            overlap = body & tube
            close(0 if overlap is None else overlap.volume,0,1e-6)
            close(body.distance_to(tube),0,1e-6)
            overlap = body & (Pos(0,0,sign*.5)*tube)
            volume = 0 if overlap is None else overlap.volume
            assert volume > .01, "Further insertion should meet the geometric stop."
            overinserted[end] = volume
            released = Pos(0,0,-sign)*tube
            overlap = body & released
            close(0 if overlap is None else overlap.volume,0,1e-6)
            gap = body.distance_to(released)
            assert gap > .05
            withdrawn[end] = gap
        clear_path = Pos(0,0,-1)*extrude(Circle(throat-.01),amount=height+2)
        overlap = body & clear_path
        close(0 if overlap is None else overlap.volume,0,1e-6)
        rings = {}
        for end in ('large','small'):
            rp = dict(tube_diameter=p[end+'_diameter'],clearance=p[end+'_clearance'],
                      wall=p['wall'],height=8,lead_in=p['lead_in'])
            ring = ring_module.build(**rp)
            sound(ring)
            close(ring.volume,socket_ring_volume(rp),.001)
            gauge = Pos(0,0,-1)*extrude(Circle(rp['tube_diameter']/2),amount=10)
            overlap = ring & gauge
            close(0 if overlap is None else overlap.volume,0,1e-6)
            close(ring.distance_to(gauge),rp['clearance']/2,1e-6)
            rings[end] = dict(tube_diameter_mm=rp['tube_diameter'],
                              diametral_clearance_mm=rp['clearance'],
                              measured_radial_gap_mm=ring.distance_to(gauge))
        results.append(dict(case=label,overrides=overrides,reference_tube_wall_mm=tube_wall,
                            large_end_engagement_mm=large_seat,small_end_engagement_mm=p['small_depth'],
                            minimum_adapter_bore_mm=2*throat,seated_overlap_mm3=0,contact_gap_mm=0,
                            overinserted_half_mm_overlap_mm3=overinserted,
                            withdrawn_one_mm_gap_mm=withdrawn,matching_fit_rings=rings,
                            analytic_volume_mm3=reducer_volume(p)))
    print("PASS tube reducer: three sizes; two tube seats, withdrawal, stops, open passage, matching fit rings",flush=True)
    return results


def sliding_assembly_checks():
    from build123d import Pos
    from sliding_box_common import settings,ledge_z,build_fit_channel,build_fit_slider,SLOPE
    module = load("sliding_box_assembly")
    results = []

    def verify_pair(box,lid,p,z):
        intersection = box & lid
        close(0 if intersection is None else intersection.volume,0,1e-6)
        close(box.distance_to(lid),0,1e-6)
        close(lid.bounding_box().min.Z,z)
        target = p['side_clearance']/sqrt(1+SLOPE**2)
        gaps = []
        for sign in (-1,1):
            guides = [f for f in box.faces() if f.center().Z > z+.1 and sign*f.center().Y > 0
                      and abs(f.normal_at().X) < 1e-6 and abs(f.normal_at().Z+SLOPE/sqrt(1+SLOPE**2)) < 1e-6]
            sides = [f for f in lid.faces() if sign*f.center().Y > 0
                     and abs(f.normal_at().X) < 1e-6 and abs(f.normal_at().Z-SLOPE/sqrt(1+SLOPE**2)) < 1e-6]
            assert guides and sides
            guide,side = max(guides,key=lambda f:f.area),max(sides,key=lambda f:f.area)
            gap = guide.distance_to(side)
            close(gap,target,1e-5)
            gaps.append(gap)
        raised = box & (Pos(0,0,p['side_clearance']/SLOPE+.5)*lid)
        assert raised is not None and raised.volume > .01, "The guides must obstruct a vertical lift."
        return gaps

    for label,overrides in (("default",{}),("compact",SLIDING_COMPACT),("large",SLIDING_LARGE)):
        p = settings(overrides)
        max_open = p['length']-p['wall']-p['end_clearance']-20
        for opening in (0,30,max_open):
            assembly = module.build(open_distance=opening,**p)
            assert assembly.is_valid and len(assembly.solids()) == 2
            box,lid = assembly.children
            gaps = verify_pair(box,lid,p,ledge_z(p,p['height']))
            if opening == 0:
                close(p['length']/2-p['wall']-lid.bounding_box().max.X,p['end_clearance'])
            results.append(dict(case=label,open_distance_mm=opening,rigid_part_overlap_mm3=0,
                                normal_side_gaps_mm=gaps,support_contact=True,vertical_lift_blocked=True))
        channel = build_fit_channel(**p)
        slider = Pos(-p['pull_extension']/2,0,ledge_z(p,p['sample_height']))*build_fit_slider(**p)
        assert channel.is_valid and slider.is_valid
        gaps = verify_pair(channel,slider,p,ledge_z(p,p['sample_height']))
        results.append(dict(case=label+"_fit_sample",rigid_part_overlap_mm3=0,
                            normal_side_gaps_mm=gaps,support_contact=True,vertical_lift_blocked=True))
    print("PASS sliding set: three sizes, three lid positions per size, matching fit samples; no overlap, guide gaps, support contact, retained lid",flush=True)
    return results


def ruler_assembly_checks():
    from build123d import Pos
    from ruler_stop_common import settings, engagement
    module = load("ruler_stop_assembly")
    results = []
    for label,overrides,reference_length in (("default",{},180),("compact",RULER_COMPACT,140),
                                             ("large",RULER_LARGE,220)):
        p = settings(overrides)
        assembly = module.build(reference_length=reference_length,**overrides)
        assert assembly.is_valid and len(assembly.solids()) == 3
        body,ruler,wedge = assembly.children
        for a,b in ((body,ruler),(body,wedge),(ruler,wedge)):
            intersection = a & b
            close(0 if intersection is None else intersection.volume,0,1e-6)
            close(a.distance_to(b),0,1e-6)
        depth = engagement(p)
        close(body.bounding_box().min.X,0)
        close(body.bounding_box().max.X,p['body_length'])
        close(ruler.bounding_box().min.Z,p['floor'])
        close(wedge.bounding_box().min.Z,p['floor']+p['ruler_thickness'])
        close(wedge.bounding_box().max.X,depth)
        tip_gap = p['body_length']-wedge.bounding_box().max.X
        grip_gap = p['wedge_length']-p['grip_length']-depth
        assert 1 <= tip_gap <= 5 and grip_gap >= 4
        ceiling = p['floor']+p['ruler_thickness']+p['clamp_gap']
        roofs = [f for f in body.faces() if abs(f.center().Z-ceiling) < 1e-6 and f.normal_at().Z < -.999]
        assert len(roofs) == 1
        close(roofs[0].distance_to(wedge),0,1e-6)
        slot_width = p['ruler_width']+p['side_clearance']
        span = slot_width-2*p['wedge_side_clearance']
        ruler_gaps,wedge_gaps = [],[]
        for sign in (-1,1):
            sides = [f for f in body.faces() if abs(f.center().Y-sign*slot_width/2) < 1e-6
                     and sign*f.normal_at().Y < -.999]
            ruler_sides = [f for f in ruler.faces() if abs(f.center().Y-sign*p['ruler_width']/2) < 1e-6
                           and sign*f.normal_at().Y > .999]
            wedge_sides = [f for f in wedge.faces() if abs(f.center().Y-sign*span/2) < 1e-6
                           and sign*f.normal_at().Y > .999]
            assert sides and ruler_sides and wedge_sides
            ruler_gap = min(a.distance_to(b) for a in sides for b in ruler_sides)
            wedge_gap = min(a.distance_to(b) for a in sides for b in wedge_sides)
            close(ruler_gap,p['side_clearance']/2,1e-6)
            close(wedge_gap,p['wedge_side_clearance'],1e-6)
            ruler_gaps.append(ruler_gap)
            wedge_gaps.append(wedge_gap)
        pushed = body & (Pos(.5,0,0)*wedge)
        assert pushed is not None and pushed.volume > .01
        pulled = Pos(-.5,0,0)*wedge
        released_gap = body.distance_to(pulled)
        assert released_gap > .005
        contains(body.solids()[0],(p['body_length']-.05,0,p['floor']-.05),True)
        contains(body.solids()[0],(p['body_length']+.05,0,p['floor']-.05),False)
        results.append(dict(case=label,overrides=overrides,reference_length_mm=reference_length,
                            rigid_part_overlap_mm3=0,engagement_mm=depth,tip_to_reference_face_mm=tip_gap,
                            grip_to_body_mm=grip_gap,ruler_side_gaps_mm=ruler_gaps,wedge_side_gaps_mm=wedge_gaps,
                            extra_half_mm_insertion_overlap_mm3=pushed.volume,
                            half_mm_withdrawal_clearance_mm=released_gap))
    print("PASS ruler stop: three sizes; ruler/floor/wedge contacts, side gaps, exposed grip, clear reference face, insertion/withdrawal geometry",flush=True)
    return results


def sanding_assembly_checks():
    from sanding_common import engagement, slot_centers
    module = load("sanding_assembly")
    results = []
    for label,overrides in (("default",{}),("compact",SANDING_COMPACT),("large",SANDING_LARGE)):
        p = module.settings(overrides)
        shape = module.build(**overrides)
        assert shape.is_valid and len(shape.solids()) == 3
        block,left,right = shape.children
        for a,b in ((block,left),(block,right),(left,right)):
            intersection = a & b
            close(0 if intersection is None else intersection.volume,0,1e-6)
        depth = engagement(p)
        for x,wedge in zip(slot_centers(p),(left,right)):
            close(block.distance_to(wedge),0,1e-6)
            close(wedge.bounding_box().min.Z,p['height']-depth)
            sign = -1 if x < 0 else 1
            center = x-sign*p['paper_thickness']/2
            # At the actual mouth, the wedge leaves one paper-thickness gap
            # against the outside wall and touches the opposite edge.
            half_width = (p['slot_width']-p['paper_thickness'])/2
            outer_wall = x+sign*p['slot_width']/2
            outer_wedge = center+sign*half_width
            close(abs(outer_wall-outer_wedge),p['paper_thickness'])
            for offset,material in ((-.01,True),(.01,False)):
                contains(wedge.solids()[0],(center+sign*(half_width+offset),0,p['height']),material)
            contains(block.solids()[0],(outer_wall+sign*.01,0,p['height']-.01),True)
            # A paper tab as wide as the wedge fits between the rounded slot
            # ends. Probe its centerline near both ends as well as the middle.
            tab_half = (p['slot_span']-2*p['wedge_end_clearance'])/2
            for y in (-tab_half+.01,0,tab_half-.01):
                paper = (outer_wall-sign*p['paper_thickness']/2,y,p['height']-.01)
                contains(block.solids()[0],paper,False)
                contains(wedge.solids()[0],paper,False)
        bottom_clearance = p['slot_depth']-depth
        assert bottom_clearance >= 2 and p['wedge_height']-depth >= 5
        results.append(dict(case=label,overrides=overrides,rigid_part_overlap_mm3=0,
                            paper_gap_mm=p['paper_thickness'],engagement_mm=depth,
                            wedge_bottom_clearance_mm=bottom_clearance,
                            wedge_grip_above_block_mm=p['wedge_height']-depth))
    print("PASS sanding_assembly: three sizes; paper gap, mouth contact, bottom clearance, no overlap",flush=True)
    return results


def assembly_checks():
    module = load("soap_dish_assembly")
    results = []
    for label, overrides in (("default", {}), ("compact", {"length": 80, "width": 60, "height": 12, "foot_height": 6}),
                             ("large", {"length": 200, "width": 140, "height": 24, "foot_height": 16})):
        p = module.settings(overrides)
        assembly = module.build(**overrides)
        assert assembly.is_valid and len(assembly.solids()) == 2
        assert all(s.volume > 0 for s in assembly.solids())
        tray, insert = assembly.children
        collision = tray & insert
        intersection_volume = 0 if collision is None else collision.volume
        close(intersection_volume, 0, 1e-6)
        close(tray.distance_to(insert), 0, 1e-6)
        close(insert.bounding_box().min.Z, p['floor'])
        close(insert.bounding_box().max.Z, p['floor']+p['foot_height']+p['plate'])
        close(tuple(assembly.bounding_box().size), (p['length'], p['width'], p['height']))
        # Probe every actual contact foot immediately above the common floor.
        from soap_dish_common import foot_centers
        for x, y in foot_centers(p):
            contains(insert.solids()[0], (x, y, p['floor']+.01), True)
            contains(tray.solids()[0], (x, y, p['floor']-.01), True)
        results.append(dict(case=label, overrides=overrides, intersection_volume_mm3=intersection_volume,
                            minimum_part_distance_mm=tray.distance_to(insert),
                            feet_contact_z_mm=insert.bounding_box().min.Z,
                            side_clearance_mm=(p['length']-2*p['wall']-insert.bounding_box().size.X)/2))
    print("PASS soap_dish_assembly: three sizes; four feet contact floor; no overlap; side clearance", flush=True)
    return results


def mesh_checks(name, shape):
    report = {}
    for extension in ("stl", "3mf"):
        mesh = trimesh.load(ROOT / f"{name}.{extension}", force="mesh")
        assert mesh.is_watertight and mesh.is_winding_consistent
        assert mesh.body_count == 1 and mesh.volume > 0
        close(mesh.extents, tuple(shape.bounding_box().size), .01)
        assert abs(mesh.volume / shape.volume - 1) < .001
        downward = (mesh.face_normals[:, 2] < -.707107) & (mesh.triangles_center[:, 2] > .01)
        report[extension] = dict(watertight=True, consistent_winding=True, connected_bodies=1,
                                 bounds_mm=mesh.extents.tolist(), volume_mm3=float(mesh.volume),
                                 bed_z=float(mesh.bounds[0, 2]),
                                 downward_area_above_bed_mm2=float(mesh.area_faces[downward].sum()))
    return report


def main():
    from build_collection import NAMES,ASSEMBLIES
    assert set(CASES) == set(NAMES), "Each print file needs a matching validation case."
    results = {}
    for name, (bounds, compact, large, bad) in CASES.items():
        module = load(name)
        shape = module.gen_step()
        sound(shape)
        close(tuple(shape.bounding_box().size), bounds)
        features = default_features(name, shape)
        assert features, f"Missing functional probes for {name}"
        variants = []
        alternate_cases = [("compact",compact),("large",large)]
        if name == 'divider_joint':
            alternate_cases.append(('straight',{'ports':(0,180)}))
        for label, overrides in alternate_cases:
            variant = module.build(**(module.PARAMETERS | overrides))
            sound(variant)
            detail = dict(case=label,overrides=overrides,
                          bounds_mm=tuple(variant.bounding_box().size),volume_mm3=variant.volume)
            if name == 'divider_joint':
                detail['feature_checks'] = divider_joint_features(variant,module.PARAMETERS | overrides)
            elif name == 'sorting_sieve':
                detail['feature_checks'] = sieve_features(variant,module.PARAMETERS | overrides,
                                                         85 if label=='compact' else 61)
            elif name == 'sieve_aperture_coupon':
                detail['feature_checks'] = aperture_coupon_features(variant,module.PARAMETERS | overrides)
            variants.append(detail)
        try:
            module.build(**(module.PARAMETERS | bad))
        except ValueError:
            pass
        else:
            raise AssertionError(f"{name} accepted invalid parameters {bad}")
        results[name] = dict(bounds_mm=bounds, volume_mm3=shape.volume, feature_checks=features,
                             variants=variants, invalid_parameters_rejected=bad,
                             mesh=mesh_checks(name, shape))
        print(f"PASS {name}: default features, {len(alternate_cases)} alternate configurations, invalid input, STL/3MF", flush=True)
    output = ROOT / "review" / "design_validation.json"
    geometry_files = [ROOT/f"{name}{ext}" for name in NAMES for ext in (".step.py",".step",".stl",".3mf")]
    geometry_files += [ROOT/f"{name}{ext}" for name in ASSEMBLIES for ext in (".step.py",".step")]
    geometry_files += list(ROOT.glob("*_common.py"))
    fingerprints = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in geometry_files}
    output.write_text(json.dumps({"physical_print_tested": False, "models": results,
                                 "validated_files_sha256": fingerprints,
                                 "soap_dish_assembly": assembly_checks(),
                                 "sanding_assembly": sanding_assembly_checks(),
                                 "sliding_assembly": sliding_assembly_checks(),
                                 "ruler_stop_assembly": ruler_assembly_checks(),
                                 "tube_reducer_fit": reducer_fit_checks(),
                                 "strap_clamp_assembly": strap_assembly_checks(),
                                 "divider_joint_assembly": divider_assembly_checks()}, indent=2), encoding="utf-8")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
