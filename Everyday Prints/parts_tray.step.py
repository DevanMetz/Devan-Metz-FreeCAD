"""Divided parts tray. Units mm; XY centered; bottom Z=0. Apache-2.0."""
from build123d import Color, Pos, RectangleRounded, extrude

PARAMETERS = dict(length=150.0, width=100.0, height=24.0, columns=3, rows=2,
                  wall=2.4, floor=2.0, outer_radius=4.4, pocket_radius=2.0)


def build(*, length=150.0, width=100.0, height=24.0, columns=3, rows=2,
          wall=2.4, floor=2.0, outer_radius=4.4, pocket_radius=2.0):
    if not (30 <= length <= 250 and 30 <= width <= 250 and 8 <= height <= 80):
        raise ValueError("Use length/width 30–250 and height 8–80 mm.")
    if not (isinstance(columns, int) and isinstance(rows, int)
            and 1 <= columns <= 8 and 1 <= rows <= 8):
        raise ValueError("Rows and columns must be integers from 1 to 8.")
    if not (1.6 <= wall <= 5 and 1.2 <= floor <= 5 and height > floor + 3):
        raise ValueError("Use wall 1.6–5, floor 1.2–5, and height > floor + 3.")
    cell_x = (length - (columns + 1) * wall) / columns
    cell_y = (width - (rows + 1) * wall) / rows
    if min(cell_x, cell_y) < 8:
        raise ValueError("Each compartment must be at least 8 mm wide.")
    if not (0 < pocket_radius < min(cell_x, cell_y) / 2
            and wall <= outer_radius < min(length, width) / 2
            and outer_radius <= wall + pocket_radius):
        raise ValueError("Corner radii must fit pockets and preserve outer walls.")
    body = extrude(RectangleRounded(length, width, outer_radius), amount=height)
    pockets = []
    for col in range(columns):
        for row in range(rows):
            x = -length / 2 + wall + cell_x / 2 + col * (cell_x + wall)
            y = -width / 2 + wall + cell_y / 2 + row * (cell_y + wall)
            pocket = extrude(RectangleRounded(cell_x, cell_y, pocket_radius),
                             amount=height - floor + 1)
            pockets.append(Pos(x, y, floor) * pocket)
    body = body - pockets
    body.label = f"parts_tray:{columns}x{rows}_open_pockets"
    body.color = Color(0.025, 0.29, 0.26)
    return body


def gen_step():
    return build(**PARAMETERS)
