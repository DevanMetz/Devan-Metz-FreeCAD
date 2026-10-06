# CAD visual review

Reviewed isometric, opposing underside, top, and front snapshots for all forty-six
printable parts and all five reference assemblies. The rendered geometry agrees with
the intended parts, including pocket counts, open slot ends, relief cuts,
pouring notch, foot locations, and print orientation.

The review prompted two functional repairs: the divider coupon now has open
ends for full-length boards, and the tray's outside corner radius preserves the
specified wall thickness. Both were regenerated, checked, and reviewed again.

Mesh inspection prompted a third repair: the tube squeezer's entrance bevels
were made shallower to allow for curved-face tessellation near a 45-degree
overhang. Its working throat remains 64 × 2 mm. Source probes and analytic
volume checks cover both lead-ins.

The soap-dish insert is shown feet upward in its print file and feet downward in
the reference assembly. Four feet touch the tray floor; exact solid intersection
volume is zero. CLI face alignment confirms zero Z offset at the contact plane.
CLI face measurement confirms 8 mm beneath the insert plate. Side clearance is
1 mm per side; compact and large assembly cases also pass.

The five later additions also match their intended use and orientation. The
label stand's slot opens at both ends, leans through the upper body, and retains
its flat floor. The finishing pyramid has a small flat tip and a continuous
rounded base. The winder has two opposing parking notches, a center tie slot,
and a continuous waist. All eighteen rack sockets are present with closed
floors and entry bevels. The matching coupon shows three sockets and one, two,
and three distinct top marks in increasing-clearance order. Underside views
show continuous bed faces on all five parts.

The sanding block shows two closed-end clamp slots, a separate grip recess,
chamfered wrap edges, and an uninterrupted sole. The wedge prints narrow tip
down. The reference assembly places both wedges above the slot floors and
leaves their tops accessible. Instructions specify narrower paper-end tabs to
clear the closed slot ends. Geometry checks verify clearance for these tabs.
Friction and paper compressibility have not been measured.

The C-shaped grommet shows an uninterrupted side opening through flange and
sleeve, an entry bevel at the flange, and a tapered sleeve tip. Its first export
exceeded the 0.01 mm mesh-dimension tolerance by about 0.013 mm; refining the
tessellation brought the final mesh into tolerance. The build script now
requests 0.005 linear and 0.05 angular mesh deflection explicitly.

The radius template has four visibly distinct corner arcs, one through four
recessed ticks, and a central finger hole. Independent radial probes and volume
checks verify the default R5/R10/R15/R20 arcs and all tick cutouts.

The center finder shows two equal upright pins and a centered through-hole
with its wider entry on the bed side. Geometric contact probes cover 20, 45,
and 72 mm stock widths. The brush rest has three matched pairs of cradles, six
peaked openings under them, a continuous catch floor, and a front pouring lip.
The utility peg has two clear mounting holes, a widened root, and a tapered
retaining head. An analytic-volume mismatch identified an unintended ledge
under its head; the overlapping cap was corrected and the source, meshes, and
views were regenerated. The final profile has a continuous taper.

The sliding box shows two continuous guide rails, support ledges, a front entry,
and a closed back stop. Its lid has angled edges, a lower rear lead, and an
accessible pull grip. The short channel and slider visibly repeat the same
cross-section. The assembly renders show the lid 30 mm open while still held
between the rails. Kernel face-distance checks measure 0.23426 mm normal gaps
on both sides at the default setting. Three sizes at three slide positions
and the three fit pairs have no rigid-part overlap, maintain support contact,
and obstruct a straight vertical lift. Physical sliding force is untested.

The round-stock cradle shows two continuous V faces, open ends, four mounting
holes, and a flat base. Its measured contact geometry matches 6, 25, and 50 mm
round stock at the default size. The tie anchor shows four side openings into
its two perpendicular peaked passages, with the mounting holes clear of those
passages. Its underside remains closed except for the mounting holes. The
funnel shows a continuous cone, cylindrical spout, wide rim, and an external
hanging tab. Its supplied orientation places the mouth on the bed; it must be
turned over for use. Bore and wall probes confirm the open material path.

The folded-bag clip shows a continuous U root, tapered arms, rounded nose bends,
and a flared open mouth. Kernel distance between the front arms measures its
unloaded throat at 0.609028 mm. The cord clip shows an open C-shaped cavity,
rounded entry tips, and a flat adhesive back. A virtual seated 6 mm cord has
0.3 mm radial clearance and no overlap; moving it toward the 5.2 mm entry
produces interference, confirming that insertion needs arm deflection. Both
sources print their entire end profiles on the bed with the bend plane in XY.
These are unstrained flexure prototypes; no elastic or fatigue result is claimed.

The hand knob has six rounded lobes, blended valleys, a centered hex pocket,
and an open bolt bore through the flat underside. A virtual 10 mm across-flat,
5 mm thick nut seats on the pocket floor with zero overlap and 0.4 mm recess
below the top. The shim has two constant-thickness arms, a semicircular slot
end, a closed back, and a separate hanging hole. Probes confirm its 2 mm
thickness and slot access; independent area-times-thickness volume agrees
with the solid. Both designs remain physical prototypes.

The marking saddle shows two parallel fences and separated straight/diagonal
through-slots in the plate. Its print orientation puts the complete plate on
the bed. The 38.5 mm fence gap, both 1 mm guide widths, 90/45-degree directions,
board seating, and analytic volume pass the functional checks. The roll adapter
shows six connected spokes, open sectors, a broad lower flange, and a tapered
upper rim with a continuous axle bore. Two virtual copies contact opposite
ends of a 50 mm-wide roll without overlap and leave 20 mm between their tips.
The seated 8 mm rod has 0.3 mm radial clearance through both. Printing and
physical marking/rotation performance are still untested.

The bookend has an unobstructed planar book face, two rear braces, two pointed
windows, and a continuous broad foot with a tapered front edge. Its rear
braces connect outside the window openings. Functional probes and an independent
volume calculation, including the bevel across rounded footprint corners,
agree with the model. The corner cable guide has a continuous curved floor,
inner and outer walls, two open ports, and two separate mounting ears. A
virtual 8 mm cable following a 30 mm centerline radius contacts the floor
without intersecting the guide, and lifts through the open top without overlap.
Both are in their intended foot/floor-down print orientations. Stability and
holding performance require physical trials.

The scoop has a continuous rounded bowl, lowered front pouring notch, low
handle, and hanging hole. Independent area-times-depth calculation and a
virtual fill solid agree on 30.027645 mL below the 16 mm lip; the fill has no
overlap with the print. The plant marker has a blank rounded head, blended
neck, tapered stake with a small flat tip, and a hanging hole. Its initial
stake extrusion pointed below the label; explicit +Z extrusion corrected the
orientation. The final source has uniform 2.4 mm thickness on Z=0, and its
analytic volume includes the neck blends and hanging hole. Both previews
match the supplied print orientation. Physical use remains untested.

The ruler-stop body shows a continuous through-passage in its end-down print
orientation. The wedge has a flat lower face, shallow taper, and raised grip.
The assembly shows the body around an unmarked gray reference ruler, with the
orange wedge above it and its grip outside. At three sizes, all three parts
have zero volumetric overlap and the intended floor, ruler, and mouth contacts.
The default ruler has 0.2 mm clearance at each side; wedge side gaps are 1.2 mm.
The wedge tip remains 1.727 mm behind the reference face, and the grip begins
9.727 mm outside the body. A further 0.5 mm insertion causes interference,
while a 0.5 mm withdrawal clears the roof. Copied-source export checks also
rebuild both print files and the assembly with a different ruler size. Force,
friction, and physical repeatability remain untested.

The tube reducer shows two straight sockets, a continuous conical transition,
open mouths with entry leads, and an annular small-end stop visible from above.
Its larger mouth rests on the bed. The fit ring shows the same working bore
and entry leads on both ends, with a flat annular bed face. The labeled section
drawing distinguishes the printed walls from illustrative tubes and shows the
socket depths and seating conditions. Default 50 and 32 mm tubes seat without
overlap at 22.545 and 20 mm insertion, respectively. Two additional sizes also
pass contact, withdrawal, over-insertion, continuous bore, matching ring, and
analytic volume checks. Physical retention and leakage remain untested.

The strap corner has two perpendicular workpiece faces, an open circular
corner relief, a rounded outer path, and two projecting guide lips. The upper
lip has a visible sloped underside. Its broad lower lip sits on the bed. The
assembly shows four teal pads against a gray frame with an orange strap loop;
the reference components are distinct from the print files. Three sizes have
zero component overlap, eight planar frame contacts, contact between every
pad and the strap, and the intended guide gaps. Default gaps are 1 mm above
and below the strap; lips extend 0.8 mm beyond its thickness. Vertical strap
movement meets the lips, and the integrated pad volume matches CAD. These
are geometric checks, with no physical force or retention result.

The sorting sieve shows 97 circular openings in a connected flat floor, an
unbroken surrounding wall, and a low handle with a semicircular end and hanging
hole. The handle root remains outside the hole field. Its entire lower face
sits on the bed. The aperture coupon shows three straight through-holes with
one, two, and three recessed identification ticks; its underside is flat.
At three sizes, the sieve checks all actual bore diameters, floor webs, wall
margins, and handle continuity. Smaller virtual spheres pass through at three
locations, while larger spheres contact the rim without overlap and encounter
interference if pushed farther. The default 3.8/4.2 mm sphere cases bracket
the 4 mm apertures. Independent volume calculations agree with the sieve and
coupon solids. Physical sorting performance and printed accuracy remain untested.

The divider joint has four open branches with continuous floors, parallel
slot walls, top entry leads, and a solid central hub. Its underside sits flat
on the bed. The assembly shows four distinct gray board segments ending at
the hub, with the brown connector supporting their lower ends. Cross, T,
corner, and straight modes pass slot probes and independent volume checks.
Three reference arrangements show floor/backstop contact, total board
clearance, zero component overlap, withdrawal clearance, and interference
on over-insertion or lowering below the floor. Physical retention is untested.

Final checks cover 142 printable parameter configurations and 30 assembly/fit
configurations. All 94 default STL/3MF exports have one connected,
watertight body and consistent winding. The mesh scan found no downward faces
above the bed steeper than 45 degrees from vertical in the supplied print
orientations. Slicer preview and physical trials are still necessary.

Snapshots show CAD geometry, not photographs of printed parts. No physical
printing, load, fit, surface-finish, or water-retention test has been performed.
