"""Funnel for dry workshop supplies; print wide mouth down, then invert. mm."""
from build123d import Circle, Color, Pos, RectangleRounded, extrude, loft

PARAMETERS = dict(mouth_diameter=70.0,spout_diameter=10.0,cone_height=40.0,
                  spout_length=20.0,wall=2.0,rim_extra=2.0,rim_height=3.0,hanger_hole=4.5)


def build(*,mouth_diameter=70.0,spout_diameter=10.0,cone_height=40.0,
          spout_length=20.0,wall=2.0,rim_extra=2.0,rim_height=3.0,hanger_hole=4.5):
    if not (30 <= mouth_diameter <= 120 and 6 <= spout_diameter <= 35
            and 20 <= cone_height <= 80 and 8 <= spout_length <= 40 and 1.6 <= wall <= 3
            and 1.5 <= rim_extra <= 4 and 2.4 <= rim_height <= 5 and 3 <= hanger_hole <= 6):
        raise ValueError("Funnel or hanger dimensions outside supported ranges.")
    slope = (mouth_diameter-spout_diameter)/2/cone_height
    if mouth_diameter < spout_diameter+12 or not 0 < slope <= .8 or rim_height >= cone_height/3:
        raise ValueError("Keep a useful cone and limit its print overhang to 38.7 degrees from vertical.")
    mouth,spout = mouth_diameter/2,spout_diameter/2
    rim = mouth+wall+rim_extra
    body = loft([Circle(mouth+wall),Pos(0,0,cone_height)*Circle(spout+wall)])
    body += Pos(0,0,cone_height)*extrude(Circle(spout+wall),amount=spout_length)
    body += extrude(Circle(rim),amount=rim_height)
    body += Pos(rim+3,0,0)*extrude(RectangleRounded(16,12,3),amount=rim_height)
    cavity = loft([Pos(0,0,-1)*Circle(mouth+slope),Pos(0,0,cone_height)*Circle(spout)])
    bore = Pos(0,0,-1)*extrude(Circle(spout),amount=cone_height+spout_length+2)
    body = body-cavity-bore
    body -= Pos(rim+5,0,-1)*extrude(Circle(hanger_hole/2),amount=rim_height+2)
    body.label = "workshop_funnel:mouth_down_continuous_cone_spout_external_hanger"
    body.color = Color(.065,.33,.34)
    return body


def gen_step():
    return build(**PARAMETERS)
