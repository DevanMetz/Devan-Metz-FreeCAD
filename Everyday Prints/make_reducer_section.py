"""Draw the default reducer section and illustrative tube seats; no CAD edits."""
import importlib.util
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon,Rectangle

ROOT = Path(__file__).resolve().parent


def main():
    spec = importlib.util.spec_from_file_location("tube_reducer",ROOT/"tube_reducer.step.py")
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    p = source.PARAMETERS
    big = (p['large_diameter']+p['large_clearance'])/2
    small = (p['small_diameter']+p['small_clearance'])/2
    throat = small-p['stop_inset']
    shoulder = p['large_depth']+p['transition_length']
    height = shoulder+p['small_depth']
    entry = p['lead_in']/.8
    seat = p['large_depth']+p['large_clearance']/2/((big-throat)/p['transition_length'])
    section = [(big+p['lead_in'],0),(big+p['wall'],0),(big+p['wall'],p['large_depth']),
               (small+p['wall'],shoulder),(small+p['wall'],height),
               (small+p['lead_in'],height),(small,height-entry),(small,shoulder),
               (throat,shoulder),(big,p['large_depth']),(big,entry)]
    ink,teal,gray,paper = '#17343a','#277c7c','#b9c2c7','#f4f7f7'
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'svg.fonttype':'none'})
    fig = plt.figure(figsize=(12,9),facecolor=paper)
    fig.text(.06,.94,'TUBE REDUCER / FIT AND SEATING',fontsize=22,weight='bold',color=ink)
    fig.text(.06,.902,f'Axial section of the default design · {2*(big+p["wall"]):g} mm outside diameter × {height:g} mm high',
             fontsize=12,color=ink)
    ax = fig.add_axes([.03,.15,.59,.70],facecolor=paper)
    for sign in (-1,1):
        ax.add_patch(Polygon([(sign*x,z) for x,z in section],closed=True,
                             facecolor=teal,edgecolor=ink,linewidth=1.1,hatch='///'))
        for radius,bottom,top in ((p['large_diameter']/2,-10,seat),
                                   (p['small_diameter']/2,shoulder,height+10)):
            x0 = radius-p['stop_inset'] if sign > 0 else -radius
            ax.add_patch(Rectangle((x0,bottom),p['stop_inset'],top-bottom,
                                   facecolor=gray,edgecolor='#647780',linewidth=.8))
    ax.plot([0,0],[-20,height+19],color='#97a8ad',linewidth=.8,linestyle='--')
    ax.set_aspect('equal')
    ax.set_xlim(-48,52)
    ax.set_ylim(-22,height+20)
    ax.axis('off')

    def vertical_dimension(low,high,text):
        x = -36
        ax.annotate('',(x,high),(x,low),arrowprops=dict(arrowstyle='<->',color=ink,lw=.9))
        ax.text(x-2.5,(low+high)/2,text,ha='center',va='center',rotation=90,fontsize=10,color=ink)
        ax.plot([x-1,-big-p['wall']-1],[low,low],color='#97a8ad',lw=.7)
        ax.plot([x-1,-big-p['wall']-1],[high,high],color='#97a8ad',lw=.7)

    vertical_dimension(0,p['large_depth'],f'{p["large_depth"]:g} socket')
    vertical_dimension(p['large_depth'],shoulder,f'{p["transition_length"]:g} transition')
    vertical_dimension(shoulder,height,f'{p["small_depth"]:g} socket')
    for diameter,z,label in ((p['large_diameter'],-16,'large tube OD'),
                             (p['small_diameter'],height+15,'small tube OD')):
        ax.annotate('',(diameter/2,z),(-diameter/2,z),arrowprops=dict(arrowstyle='<->',color=ink,lw=.9))
        ax.text(0,z+2.1,f'{diameter:g} {label}',ha='center',fontsize=10,color=ink)
    ax.annotate('Taper\ncontact',(p['large_diameter']/2,seat),(34,27),fontsize=10,color=ink,
                arrowprops=dict(arrowstyle='-',color=ink,lw=.9),va='center')
    ax.annotate('Flat\nstop',(small-p['stop_inset']/2,shoulder),(32,56),fontsize=10,color=ink,
                arrowprops=dict(arrowstyle='-',color=ink,lw=.9),va='center')
    ax.annotate(f'{2*throat:g} min.\nbore',(0,shoulder-.8),(0,40),fontsize=10,color=ink,
                ha='center',arrowprops=dict(arrowstyle='-',color=ink,lw=.9))
    right = fig.add_axes([.66,.17,.30,.66],facecolor=paper)
    right.axis('off')
    for y,color,label in ((.97,teal,'Printed reducer'),(.90,gray,'Reference tubes')):
        right.add_patch(Rectangle((0,y-.026),.05,.035,facecolor=color,edgecolor=ink,lw=.6))
        right.text(.08,y,label,va='center',fontsize=12,color=ink)
    blocks = [(.78,'LARGE END',f'{2*big:g} mm socket for a {p["large_diameter"]:g} mm tube.\n'
                              f'The taper contacts the end after\n{seat:.2f} mm of insertion.'),
              (.57,'SMALL END',f'{2*small:g} mm socket for a {p["small_diameter"]:g} mm tube.\n'
                              f'The flat stop sets {p["small_depth"]:g} mm insertion.\n'
                              f'Illustrated tube walls: {p["stop_inset"]:g} mm.'),
              (.35,'FIT FIRST','Print a socket fit ring for each\nmeasured tube diameter. Clearance\nadds to the whole diameter; the\n'
                              f'default {p["large_clearance"]:g} mm adds {p["large_clearance"]/2:g} mm per side.'),
              (.10,'PRINT ORIENTATION','Large mouth on the bed.\nSmall socket faces upward.')]
    for y,title,body in blocks:
        right.text(0,y,title,fontsize=12,weight='bold',color=teal)
        right.text(0,y-.035,body,va='top',fontsize=11,linespacing=1.5,color=ink)
    fig.text(.06,.057,'Unsealed slip-fit prototype. Physical fit, leakage, and retention are untested.',fontsize=11,color=ink)
    fig.text(.06,.025,'EVERYDAY PRINTS · Original parametric CAD · Apache-2.0 · Dimensions in mm',fontsize=9,color='#647780')
    for extension in ('svg','png'):
        fig.savefig(ROOT/f'tube_reducer_section.{extension}',dpi=170,facecolor=paper)
    plt.close(fig)
    print('Saved tube_reducer_section.svg and .png')


if __name__ == '__main__':
    main()
