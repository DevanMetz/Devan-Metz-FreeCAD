"""Trial flexure clip for a folded bag; print the complete side profile flat. mm."""
from build123d import Axis, CenterArc, Color, Face, Line, Wire, extrude, fillet

PARAMETERS = dict(arm_length=45.0,depth=12.0,arm_thickness=2.4,root_radius=3.0,
                  jaw_gap=.6,entry_flare=2.0,nose_length=6.0,nose_radius=.4)


def build(*,arm_length=45.0,depth=12.0,arm_thickness=2.4,root_radius=3.0,
          jaw_gap=.6,entry_flare=2.0,nose_length=6.0,nose_radius=.4):
    if not (25 <= arm_length <= 80 and 8 <= depth <= 20 and 1.6 <= arm_thickness <= 3.2
            and 2.5 <= root_radius <= 5 and .4 <= jaw_gap <= 1.6 and 1 <= entry_flare <= 3.5
            and 4 <= nose_length <= 10 and .2 <= nose_radius <= .6):
        raise ValueError("Clip dimensions outside supported ranges.")
    if (arm_length < 3*nose_length or jaw_gap/2+entry_flare > root_radius
            or nose_radius > arm_thickness/3):
        raise ValueError("Preserve a useful flexing arm, flared mouth, and rounded nose thickness.")
    l,pinch,r,t = arm_length,arm_length-nose_length,root_radius,arm_thickness
    gap,mouth = jaw_gap/2,jaw_gap/2+entry_flare
    outline = Wire([
        Line((0,r),(pinch,gap)),Line((pinch,gap),(l,mouth)),
        Line((l,mouth),(l,mouth+t)),Line((l,mouth+t),(pinch,gap+t)),
        Line((pinch,gap+t),(0,r+t)),CenterArc((0,0),r+t,90,180),
        Line((0,-r-t),(pinch,-gap-t)),Line((pinch,-gap-t),(l,-mouth-t)),
        Line((l,-mouth-t),(l,-mouth)),Line((l,-mouth),(pinch,-gap)),
        Line((pinch,-gap),(0,-r)),CenterArc((0,0),r,270,-180)])
    body = extrude(Face(outline),amount=depth)
    noses = [e for e in body.edges().filter_by(Axis.Z) if e.center().X >= pinch-.01]
    body = fillet(noses,radius=nose_radius)
    body.label = "fold_clip:trial_flexure_U_root_tapered_arms_rounded_flared_noses"
    body.color = Color(.52,.22,.07)
    return body


def gen_step():
    return build(**PARAMETERS)
