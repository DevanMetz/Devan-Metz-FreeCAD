"""90/45-degree pencil guide for a measured board width. Print plate down. mm."""
from math import sqrt
from build123d import Align, Box, Color, Pos, RectangleRounded, Rot, extrude

PARAMETERS = dict(length=90.0,board_width=38.0,clearance=.5,wall=3.0,
                  plate=3.0,fence_height=20.0,mark_width=1.0)


def build(*,length=90.0,board_width=38.0,clearance=.5,wall=3.0,
          plate=3.0,fence_height=20.0,mark_width=1.0):
    if not (50 <= length <= 220 and 15 <= board_width <= 100 and .2 <= clearance <= 1.2
            and 2.4 <= wall <= 5 and 2.4 <= plate <= 5 and 10 <= fence_height <= 40
            and .8 <= mark_width <= 1.6):
        raise ValueError("Saddle dimensions outside supported ranges.")
    gap = board_width+clearance
    # The diagonal strip is clipped at both inner fence faces. At each Y,
    # its X half-width is mark_width/sqrt(2), not mark_width/2.
    if (.4*length-gap/2-mark_width*(1/sqrt(2)+.5) < 4
            or .4*length-gap/2-mark_width/sqrt(2) < 4):
        raise ValueError("Increase length to leave 4 mm between guide slots and at the diagonal ends.")
    body = extrude(RectangleRounded(length,gap+2*wall,wall/2),amount=plate+fence_height)
    body -= Pos(0,0,plate)*Box(length+2,gap,fence_height+1,
                              align=(Align.CENTER,Align.CENTER,Align.MIN))
    straight = Pos(-.3*length,0,-1)*Box(mark_width,gap,plate+2,
                                       align=(Align.CENTER,Align.CENTER,Align.MIN))
    diagonal = Pos(.1*length,0,-1)*Rot(0,0,-45)*Box(mark_width,2*(gap+4),plate+2,
                                                  align=(Align.CENTER,Align.CENTER,Align.MIN))
    diagonal &= Pos(0,0,-1)*Box(length+2,gap,plate+2,
                               align=(Align.CENTER,Align.CENTER,Align.MIN))
    body = body-straight-diagonal
    body.label = "marking_saddle:parallel_fences_90_and_45_degree_pencil_slots"
    body.color = Color(.43,.19,.085)
    return body


def gen_step():
    return build(**PARAMETERS)
