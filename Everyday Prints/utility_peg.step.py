"""Small wall peg for tie loops; print the flat mounting back down. mm."""
from build123d import Circle, Color, Pos, RectangleRounded, extrude, loft

PARAMETERS = dict(mount_spacing=44.0,end_margin=8.0,plate_width=24.0,plate_thickness=3.0,
                  mount_hole=4.4,peg_diameter=10.0,peg_length=28.0,
                  head_diameter=16.0,head_thickness=2.4)


def build(*, mount_spacing=44.0,end_margin=8.0,plate_width=24.0,plate_thickness=3.0,
          mount_hole=4.4,peg_diameter=10.0,peg_length=28.0,
          head_diameter=16.0,head_thickness=2.4):
    if not (28 <= mount_spacing <= 80 and 6 <= end_margin <= 14 and 18 <= plate_width <= 40
            and 2.4 <= plate_thickness <= 5 and 3 <= mount_hole <= 6 and 6 <= peg_diameter <= 16
            and 16 <= peg_length <= 50 and 10 <= head_diameter <= 28 and 2 <= head_thickness <= 4):
        raise ValueError("Peg or mounting parameters outside supported ranges.")
    if (head_diameter < peg_diameter+3 or plate_width < max(head_diameter+2,peg_diameter+8)
            or mount_spacing/2 < head_diameter/2+mount_hole/2+3
            or end_margin < mount_hole/2+3):
        raise ValueError("Preserve the retaining lip, mounting-hole access, and plate margins.")
    transition = (head_diameter-peg_diameter)/2/.8
    stem_length = peg_length-head_thickness-transition
    if stem_length < 8:
        raise ValueError("Leave at least 8 mm before the retaining-head taper.")
    r,head = peg_diameter/2,head_diameter/2
    body = extrude(RectangleRounded(mount_spacing+2*end_margin,plate_width,4),amount=plate_thickness)
    for x in (-mount_spacing/2,mount_spacing/2):
        body -= Pos(x,0,-1)*extrude(Circle(mount_hole/2),amount=plate_thickness+2)
    body += Pos(0,0,plate_thickness-.1)*extrude(Circle(r),amount=stem_length+.1)
    body += loft([Pos(0,0,plate_thickness)*Circle(r+2),Pos(0,0,plate_thickness+3)*Circle(r)])
    z = plate_thickness+stem_length
    body += loft([Pos(0,0,z)*Circle(r),Pos(0,0,z+transition)*Circle(head)])
    body += Pos(0,0,z+transition)*extrude(Circle(head),amount=head_thickness)
    body.label = "utility_peg:two_hole_plate_tapered_root_retaining_head"
    body.color = Color(.32,.2,.13)
    return body


def gen_step():
    return build(**PARAMETERS)
