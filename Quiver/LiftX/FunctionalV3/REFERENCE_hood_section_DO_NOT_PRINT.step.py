"""Boolean section of live geometry: cavity, cap, foam and one head envelope."""
from build123d import Compound
import quiver_common as q

def gen_step():
    keep=q.box(-100,-80,255,100,160,115)
    shapes=[(q.upper_frame(),'SECTION_HOOD','#819379'),
            (q.foam(),'SECTION_FOAM_TEMPLATE','#4B4B50'),
            (q.reference_arrow(0,0,short=True),'SECTION_35x70_HEAD_ENVELOPE','#829EA9')]
    parts=[]
    for s,label,color in shapes:
        cut=s.intersect(keep)
        if not hasattr(cut,'volume'):
            cut=q.joined(cut)
        parts.append(q.tint(q.lh(cut),label,color))
    return Compound(label='REFERENCE_SECTION_NOT_A_MANUFACTURING_PART',children=parts)
