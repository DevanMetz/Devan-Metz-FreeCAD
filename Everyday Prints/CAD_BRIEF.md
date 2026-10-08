# Everyday Prints — design brief

Original, practical parametric parts, licensed under Apache-2.0 to match this
repository. Dimensions are millimeters. These are new designs, not reproductions
of downloaded models. Python/build123d source is canonical; STEP is the primary
exchange model; STL and geometry-only 3MF are print exports.

Sources expose an editable `PARAMETERS` dictionary. The soap-dish, sanding,
sliding-box, ruler-stop, strap-corner, and divider-joint sets share dictionaries in their `_common.py` files. Independent inputs
have explicit range and relationship checks. Derived dimensions are calculated
from those inputs. All printable parts have one closed, positive-volume solid.
Reference assemblies keep their components separate. The ruler-stop reference
also includes an illustrative unmarked ruler, which is not a printed component.
The strap-clamp reference includes an illustrative frame and webbing loop.
The print bed is Z=0; every printable default fits within a 180 × 180 mm footprint.
Reference assemblies can occupy a larger area.

| Source / STEP basename | Intended use and parameters | Default print bounds |
|---|---|---|
| `parts_tray` | 150 × 100 × 24 tray; 3 columns × 2 rows; 2.4 walls; 2 floor; 4.4 outer / 2 inner corner radii. Each pocket is open upward. | 150 × 100 × 24 |
| `cable_comb` | Open slots for 3, 4, 5, 6, 8 diameter cables; 0.6 diametral allowance; 5 webs; 32 depth; 4 thick. Tape/screw the continuous rear strip to the desk with slots overhanging its edge. No snap-fit claim. | 59 × 32 × 4 |
| `divider_foot` | 3 thick divider board with 0.4 total clearance; 34 × 24 base; 2.4 floor; 20 overall height; 3 jaws with 1 lead-in. Print two or more per divider. | 34 × 24 × 20 |
| `divider_fit_coupon` | Four open-ended slots for a 3 thick board, with 0.2 / 0.4 / 0.6 / 0.8 total clearance. Top tick marks on left ribs identify slots 1–4. | 26 × 20 × 8 |
| `phone_stand` | Open triangular frame; 68° phone lean from horizontal; 15 seat depth; 96 in-use height; 85 in-use depth; 65 width; 6 frame. Printed on its side. | 85 × 96 × 65 |
| `corner_square` | 80 × 80 reference L, 18 wide legs, 8 thickness. 3 radius inner-corner relief keeps glue from the datum corner; 5 hanging hole. | 80 × 80 × 8 |
| `handle_marking_jig` | Edge fence and three 3.2 marking holes: center and ±64. Adjustable 128 pitch, 25 setback, 16 end margins, 3 fence, 4 plate, 18 fence height. Mark with pencil/awl. | 160 × 40 × 18 |
| `tube_squeezer` | Rounded body with a 64 × 2 through-slot, 0.6 entry enlargement on both faces, and entry surfaces 38.7° from vertical. | 90 × 26 × 6 |
| `soap_dish_tray` | Rounded catch tray, 2.4 wall and floor, with a lowered 12-wide front pouring lip. | 120 × 84 × 14 |
| `soap_dish_insert` | Eleven 5-wide drain slots with 3 webs, a lift notch, four 8-diameter × 8-height feet, and a 3-thick plate. Print plate down, feet up. | 113.2 × 77.2 × 11 |
| `soap_dish_assembly` | Reference assembly; tray fixed, insert turned over with a rigid contact datum at the tray floor. 1 clearance each side; 8 drainage space. Do not print assembled. | 120 × 84 × 14 |
| `label_stand` | Small sign/card holder with an open-ended 0.8 slot, 8 deep, leaning 12° from vertical. Flat 4 floor beneath the slot. | 50 × 24 × 12 |
| `paint_pyramid` | Square finishing support with a 2.4 × 2.4 flat contact tip, 44-wide pyramid base, and a rounded 2-thick foot. Print several. | 50 × 50 × 26 |
| `cable_winder` | Flat bobbin with 22-wide waist, broad 14-wide end caps, two open parking notches, and a 12 × 3 tie slot. Loose wraps for flexible cords; no gripping-force claim. | 95 × 44 × 4 |
| `hex_bit_rack` | 6 × 3 blind hex sockets on 12 pitch, 6.7 across flats, 2.4 floor, and 0.6 entry enlargement. Nominal shank size and clearance are independent inputs. | 80 × 44 × 14 |
| `hex_bit_fit_coupon` | Three sockets with 0.15 / 0.35 / 0.55 added across-flat clearance; same 11.6 working depth and entry bevel as the rack. One to three top marks identify the sockets. | 40 × 20 × 14 |
| `sanding_block` | Hand sanding support, 100 long × 50 wide × 25 high, chamfered wrap edges, two 6 × 40 blind clamp slots 14 deep, and a central grip recess. | 100 × 50 × 25 |
| `sanding_wedge` | Print two. Symmetric 3.2-to-8 taper over 20 height and 36 span. Intended to clamp one paper end in each block slot; start with 0.3 paper thickness. | 8 × 36 × 20 |
| `sanding_assembly` | Reference with two wedges positioned for one paper layer each at the outside clamp wall. Rigid datums, no overlap; friction and paper compressibility require a physical trial. | 100 × 50 × about 34.6 |
| `cable_grommet` | Sleeve for a nominal 60 circular panel opening, 0.4 diametral clearance, 2 wall, 68 flange diameter, 16 insertion depth, and a 10 side opening. Print flange down, then invert to install. | 67.63 × 68 × 18.4 |
| `radius_template` | Flat corner-marking plate: radii 5 / 10 / 15 / 20, one to four top ticks, 20 finger hole. Align straight edges with the workpiece and trace a corner. | 80 × 80 × 3 |
| `center_finder` | Equal 8-diameter pins on 80 centers and a midpoint 3.2 marking hole. Turn the pins down and rotate until they contact opposite parallel edges; maximum default stock width 72. | 100 × 24 × 16 |
| `brush_rest` | Catch tray with two transverse rests, three paired 8.6 / 12.6 / 16.6 cradles, and peaked wash-through openings below each cradle. Print floor down. | 100 × 150 × 20 |
| `utility_peg` | Wall peg for reusable tie loops and similarly small items; 60 × 24 mounting plate, 10 stem, 16 head, and two 4.4 mounting holes on 44 centers. Print mounting back down. | 60 × 24 × 31 |
| `sliding_box` | Small-parts box with a closed 2.4 floor, front lid entry, back stop, sloped side guides, and support ledges. | 120 × 80 × 32 |
| `sliding_lid` | Matching angled-edge lid; 0.3 horizontal clearance each side, 0.3 vertical profile allowance, 6 pull extension, and raised finger grip. | 123.2 × 74.6 × 5.4 |
| `sliding_fit_channel` | Short open-ended section of the same guide geometry, with a reduced lower cavity. | 30 × 80 × 16 |
| `sliding_fit_slider` | Short matching lid section with the same side profile, rear lead, and pull grip. | 36 × 74.6 × 5.4 |
| `sliding_box_assembly` | Reference with the lid 30 open. Parameter `open_distance` controls travel; parts use rigid guide datums. Print the two components separately. | 156 × 80 × 33.1 |
| `round_stock_cradle` | 90-degree V support for holding round stock during hand layout. Apex 8 above the bed, four 4 mounting holes, and open ends for long rods. | 80 × 60 × 30 |
| `tie_anchor` | Flat-backed cable-tie anchor with two perpendicular peaked tunnels and two diagonal 3.5 mounting holes. Guaranteed rectangular tunnel section 4.8 wide × 1.6 high. | 26 × 26 × 8.6 |
| `workshop_funnel` | 70 clear mouth, 10 clear spout, 2 radial wall, 40 cone height, and 20 spout length, plus a hanging tab. Print mouth down; turn over to use. | 89 × 78 × 60 |
| `fold_clip` | Trial clip for holding a folded bag closed: two 45-long tapered arms, a rounded U root, nominal 0.6 throat, and flared, rounded entries. Print the entire side profile flat. | 50.4 × 10.8 × 12 |
| `cord_clip` | Trial side-loading clip for a nominal 6 cord, 6.6 cavity, 5.2 entry, 1-thick curved arms, and a flat adhesive foot. Print one end face down. | 20 × about 9.495 × 12 |
| `hand_knob` | Six-lobed grip around an open hex-nut pocket. Measured nut 10 across flats × 5 thick, pocket 10.3 across flats × 5.4 deep, and 6.6 through-bore. | 40 × about 36.249 × 14 |
| `slotted_shim` | Removable flat spacer with an open 6.6-wide slot, 28 depth to its rounded end, 2 thickness, and a 4.5 hanging hole in the closed back. | 40 × 24 × 2 |
| `marking_saddle` | U-shaped marking guide for a 38-wide board, with 0.5 total allowance, 20-deep side fences, and separate 1-wide pencil slots at 90 and 45 degrees. Print the plate down, then turn the fences downward to use. | 90 × 44.5 × 23 |
| `roll_adapter` | Spoked adapter from a measured 52 roll bore to an 8 rod. 0.4 outer diametral clearance, 0.6 axle diametral clearance, 15 insertion depth, 60 flange, and tapered tip. Print two flange down. | 60 × 60 × 17.4 |
| `bookend` | Flat book-facing upright with two rear triangular braces, two pointed windows, and a broad foot under the books. Front foot depth 100, rear depth 30, width 80, height 130, 4 walls/floor; tapered front edge. | 130 × 80 × 130 |
| `corner_cable_guide` | Open quarter-circle channel, 25 inner radius, 10 clear width, 8 clear depth, and two 3.5 mounting holes in flat ears. Print floor down and use channel upward. | About 41.507 × 41.507 × 10.4 |
| `workshop_scoop` | Small-parts scoop with a 60 × 45 × 20 bowl, 2.4 wall/floor, 50-long low handle, rounded pouring notch at 16 height, and 4.5 hanging hole. About 30 mL nominal capacity to the lip. | 110 × 45 × 20 |
| `plant_marker` | Blank 26 × 45 rounded label, 70-long × 8-wide stake, 15-long taper to a 1.2-wide flat tip, 2.4 thickness, rounded neck, and 3.5 hanging hole. | 26 × 115 × 2.4 |
| `ruler_stop` | Sliding stop for a measured 26-wide × 1-thick ruler. 26.4-wide passage, 3 floor below the ruler, and a 2.2 wedge gap. Print an end profile down. | 34.4 × 10.2 × 24 |
| `ruler_wedge` | Matching 35-long wedge tapering from 0.8 to 3, 24 wide, with a 4-high pull grip. Print its flat lower face down. | 35 × 24 × 7 |
| `ruler_stop_assembly` | Reference stop, engaged wedge, and gray unmarked ruler. Ruler is illustrative purchased hardware, not a print file. Default engagement 22.273; tip remains 1.727 short of reference face. | 180 × 34.4 × 11 |
| `tube_reducer` | Slip-fit reducer for smooth tube ends measured at 50 and 32 outside diameter. Independent 0.4 diametral clearances, 22/20 socket depths, 30 transition, 2.4 radial wall, 2 radial small-end stop, and 0.6 entry leads. Print the large mouth down. | 55.2 × 55.2 × 72 |
| `socket_fit_ring` | Short open ring to test a measured tube diameter and diametral clearance before printing a reducer. Default 50 tube, 0.4 clearance, 2.4 wall, 8 height, and 0.6 entry leads on both ends. | 55.2 × 55.2 × 8 |
| `strap_corner` | Print four for a rectangular frame. Perpendicular faces with 30 leg reach and 27 usable contact length, 6 wall, 3 corner-relief radius, rounded outside strap path, and two guide lips for measured 25-wide × 1.2-thick webbing. Total width allowance 2; upper lip has a supported slope. | 38 × 38 × 33.5 |
| `strap_clamp_assembly` | Reference showing four pads, an illustrative 180 × 130 × 30 frame with 20 rails, and a continuous webbing loop. Gray frame and orange strap are not print files; buckle and strap tension are omitted. | 196 × 146 × 33.5 |
| `sorting_sieve` | Handheld sieve for dry craft/workshop pieces: 90 round bowl, 18 height, 2.4 floor/wall, 97 circular holes of 4 diameter on a 7 triangular pitch, 4 minimum solid margin at the wall, and a 45-long low handle with hanging hole. | 135 × 90 × 18 |
| `sieve_aperture_coupon` | Thin sample with the same 2.4 floor thickness and three apertures: 3.8 / 4 / 4.2, identified by one to three recessed ticks. Choose the actual opening before printing a full sieve. | 40 × 18 × 2.4 |
| `divider_joint` | Drawer-divider connector with selectable cardinal branches for cross, T, corner, or straight layouts. Default four ports hold separate 3-thick board ends in 3.4 slots; 16 insertion, 18 height, 2.4 floor/walls, and 0.6 top leads. Solid central hub is 8.2 wide. | 40.2 × 40.2 × 18 |
| `divider_joint_assembly` | Reference cross connector and four illustrative 80-long × 3-thick × 50-high boards. Boards contact their individual slot floors and hub backstops; they are not print files. | 168.2 × 168.2 × 52.4 |

The label stand, pyramid, winder, rack, and bit coupon use a centered XY
footprint and bottom Z=0. Parameter
checks protect slot floors, socket webs, end margins, and minimum material at
the pyramid tip. Validate open-ended card access, normal card-slot width, all
hex sockets, blind floors, tip size, and continuity of the winder waist. Review
both top and underside faces of each generated model before packaging.

Origins: footprint center for tray, comb, feet, and coupon. Lower-left datum
corner for square and phone profile. Jig X=0 is the handle center; fence inside
face is Y=3. Phone profile lies in XY, with its width extruded in +Z. Turn the
finished print onto its long lower edge to use it.

The sanding sources share `sanding_common.py`. Their parameters protect a
minimum slot floor, closed end walls, wedge side clearance, paper space, and a
positive engagement depth before the wedge bottoms out. The reference omits
the flexible paper. Verify the clamp mouth spacing and edge contact at three
sizes, plus exact absence of rigid-part overlap. The grommet is an unlatched
insert; select a real opening and check its fit. Radius-template accuracy is
limited by the printer, so verify before using a mark for layout.

The center finder depends on equal contact-pin radii and a centered marking
hole. Verify tangency and centered marking for several virtual stock widths.
Thin stock needs clearance beneath the pins. The brush-rest portals connect
the tray compartments while their 45-degree peaked roofs avoid flat bridges.
Cradle slots must leave a material web above each portal. The peg's growing
head uses a slope below 45 degrees from vertical in print orientation. Its
mounting and holding performance require physical testing.

The sliding-box set shares `sliding_box_common.py`. Side clearance is measured
horizontally at each angled face; its default normal gap is approximately
0.234. The guide slopes grow 0.8 horizontally per 1 vertically. Verify floor
and guide geometry, the front entry and rear stop, clearance along both guide
faces, bottom support contact, free sliding at several positions, and blocked
vertical lift. Repeat at compact and larger dimensions and check the short fit
pair. The lid has no latch or seal; its sliding force needs a physical trial.

Verify the cradle's two actual V faces against virtual round stock at three
diameters and keep sufficient material around every mounting hole. The tie
anchor's crossed passages must retain a closed floor and roof; the rectangular
lower portion defines guaranteed tie clearance. The funnel's inner cone must
connect continuously to the spout bore, and its hanging hole must remain
outside the material path. These parts have no tested load or flow rating.

The two flexure clips are unstrained geometry prototypes. Their spring force,
allowable deflection, fatigue life, and retention are not established by CAD
validity. Check arm continuity, rounded entrances, unloaded clearances, and
representative parameter variants. All bending is intended in the XY layer
plane; the extrusion direction is Z. Print one sample and test its actual
material response before making several.

The hand knob uses purchased hardware measured by the user; no nut-standard
dimensions are assumed. Check the six grip lobes, through-bore, pocket floor,
across-flat allowance, top entry bevel, and seating of a virtual matching nut.
The loose nut is retained only while engaged with a bolt. The shim must have
parallel faces, an open slot with a rounded end, and a continuous closed back.
Check its working thickness, slot width/depth, hole margins, and analytic volume.
Clamping torque, compressive load, and printed thickness accuracy remain untested.

The saddle's slot width is normal to each marking line. Its fence gap uses
total added width, and the two slots must stay separated with enough end
material. Verify both fence faces, the slot directions/widths, uninterrupted
fences, and the analytic solid volume. Check any printed guide against a
known square before relying on its line. The roll adapter has a continuous
axle passage and separate clearances at its outer sleeve and axle. Check
spoke continuity, open sectors, flange contact with a virtual roll end, and
absence of overlap. Use one adapter per end only when the roll is wide enough
for both insertion lengths. Fit, rotating friction, and load capacity are untested.

Keep the book-facing plane unobstructed by the rear braces. Its window roofs
must remain below the supported print slope; verify brace continuity, the
front lead, floor, and upright. Test stability with actual books and adjust
the foot width and reach to the arrangement. The cable guide must have two open ports,
a continuous floor and inner/outer walls, and mounting holes outside the
channel. Verify a virtual cable following the curved channel without overlap.
The guide has no latch; cable bend suitability, retention, and mounting loads
require a physical trial.

Check the scoop's continuous floor and walls, unobstructed cavity, lowered
front lip, handle connection, and hanging hole. Compare a virtual fill to the
lip against the cavity and calculate its geometric capacity independently.
This is a dry workshop scoop, with no calibrated-volume or liquid-retention
claim. Check the marker's label/stake continuity, minimum tip width, neck
rounding, flat bed face, and hanging-hole margins. Intended use is labeling
pots in loose growing medium; writing adhesion and exposure durability need
physical trials.

The ruler stop and wedge share `ruler_stop_common.py`. The wedge must touch
the ruler and the passage roof at the mouth without intersecting either. Its
tip must stay behind the opposite reference face, and its grip must remain
outside the body. Check total ruler side clearance, wedge side gaps, floor
contact, mouth contact, and rigid-part overlap at three sizes. A slight
further insertion should cause geometric interference; withdrawal should
clear the roof. These checks do not establish friction or clamp force.

The tube reducer takes measured outside diameters of smooth rigid tube ends,
with independent total diametral clearances. Its large socket ends in the
sloping transition; the small socket has an upward-facing annular stop. Check
the actual seating depths with virtual tubes, contact without intersection,
free withdrawal, interference on over-insertion, and the continuous through
passage. Limit inward print slopes to 0.8 horizontal per 1 vertical. Compare
an independent volume calculation to the revolved solid at three sizes.
The fit ring repeats the working bore and both entry leads; use one sample
for each tube size. This is an unsealed slip-fit prototype for dry workshop
air connections; retention, air leakage, and service performance are untested.

The strap corner must retain two perpendicular planar workpiece faces, an open
corner relief, and a rounded strap-bearing surface. Guide lips stay outside
the workpiece envelope. Check a rectangular reference frame against all four
pads, check the entire strap loop for overlap and intended contact, and verify
width/thickness clearance from the guide lips at three sizes. Vertical movement
should meet the guide lips; no clamping force, retention, or load rating follows
from those rigid geometry checks. Use for trial hand-tensioned frame assembly.
Print each pad on its broad lower lip, with the strap groove running horizontally.

The sorting sieve must have a connected perforated floor, a closed surrounding
wall, and a continuous handle outside the hole field. Preserve at least 2 mm
between adjacent openings and the specified solid margin beside the wall.
Check every hole and floor ligament at three sizes; confirm that smaller
virtual spheres pass through and larger spheres contact the aperture rim.
The coupon must repeat the floor thickness and unchamfered openings, with
unambiguous tick counts and enough material around each hole. Use for trials
with dry craft/workshop pieces. Printed aperture accuracy, sorting behavior
of irregular pieces, handle strength, and service performance are untested.

The divider joint accepts two to four distinct cardinal ports. Each branch holds
a separate board end against a solid hub; boards do not pass through the center.
Use the existing divider fit coupon to choose total board clearance. Preserve
the floor, rounded-mouth wall thickness, and supported top lead slopes. Verify
all slots, side gaps, floor/backstop contact, free withdrawal, and interference
on over-insertion in cross, T, and corner configurations. For matching joints
with parallel facing ports, cut the board to center spacing minus hub width.
The floor raises each board by its thickness. Fit, retention, and drawer-use
performance require physical trials.

Validation: generate explicit entry sources; inspect facts, planes, positioning,
and solid validity for every model; check expected bounds and intended openings;
test representative parameter extremes and reject invalid combinations; inspect
STL/3MF watertightness, winding, body count, and orientation; save and review CAD
snapshots. No physical printing, fit, load, accuracy, or durability result is
claimed. Clearances and slicer settings are starting points to test.

## Customized cloud CAD downloads

Extend the existing export workflow without changing model geometry. A CAD ZIP
must contain a primary STEP generated from the current validated shape and the
exact applied parameters in millimeters. Printable parts also include STL and
3MF from one tessellation. Reference assemblies include their STEP and source,
with printable components supplied separately in the parts kit described below.
Preserve the existing centered XY/+Z conventions, native labels, and bed at Z=0
for print files. Include canonical Python sources, shared helpers, pinned CAD
dependencies, licensing, and a standalone rebuild command that reads the saved
parameters. Output is bounded and uses the same isolated job deadline as previews.

Verify transfer hashes, correspondence with the browser preview, STEP solid
validity/bounds/volume, print mesh watertightness and millimeter units, and rebuilds
from extracted sources. Cover scalar edits, numeric lists, helper-based parts,
and a reference assembly. Invalid inputs and stale editor downloads must remain
blocked. No physical performance claim follows from an export.

Assembly CAD downloads must also provide their printable components in the
canonical bed orientation. Transfer only shared parameter names into each
component's defaults. The kit contains one soap tray and insert; one sanding
block and two wedges; one sliding box and lid plus one channel/slider fit coupon
pair; one ruler stop and wedge; four strap corner pads; or one divider joint.
Identify fit coupons separately from assembly components, record quantities,
and exclude illustrative rulers, frames, straps, and divider boards from print
files. Verify every component's applied dimensions, one solid, bed at Z=0,
STEP/mesh consistency, and source rebuild after changing assembly dimensions.
Rebuilt parameter files must retain the kit inventory, component quantities,
and fit-coupon labels. The browser must accept continuous decimal dimensions
without restricting them to the suggested input increment; counts stay integers.
Provide recovery from pending or stalled builds without discarding edits or the
last verified preview. Stopping the wait or reaching its deadline must discard
late results, preserve download correspondence, and leave newer retries intact.
Optional 3D loading or failure must not block verified files. Label catalog-image
fallbacks clearly, display the current verified mesh after late initialization,
and preserve download integrity through graphics failures and model navigation.
Distinguish CAD building, file receipt and verification. Report actual received
bytes for original previews, rebuilt meshes and CAD ZIPs without relying on
stated lengths or displaying an unverified completion percentage. Preserve
saved-dimension and error messages with separate transfer status, stop build
reminders once file receipt starts, and keep files unavailable until verified.
Clear progress on completion, failure, Stop, deadline and model navigation. Late
bytes and obsolete requests cannot alter newer progress.
Bound original and rebuilt browser file transfers by their actual received
bytes, cancelling oversized streams before reading the remaining data. Empty
or interrupted transfers must preserve the last verified preview and allow
retrying. Stopping a pending file read must cancel it and reject late bytes.
Copy accepted nonempty chunks immediately into an owned accumulator, preserving
byte order when transport buffers are reused. Do not retain every fragment or
the larger backing buffers of borrowed views. Bound accumulator capacity by the
configured response limit, ignore empty fragments and return exactly the received
file length, without unused capacity bytes.
Validate successful response details before reading files: requested model,
parameters, units, bounds, format, hash shape and file type. Invalid details must
reject immediately without waiting for a stalled body. Cancel unused responses
after rejected details and after Stop or newer requests, without waiting for
cancellation to settle or changing newer UI state. Complete files must still
match their advertised hashes before becoming downloads. Invalid-field feedback
and mesh status must survive recovery before the first verified preview.
Validate binary STL record counts and lengths, finite normals and vertices, and
positive mesh extents before publishing a preview. Compare measured dimensions
with advertised CAD bounds, allowing 0.05 mm plus one part per million for
tessellation and single-precision coordinates. Apply these checks without the
optional renderer and preserve earlier verified files when they fail. CAD
response dimensions must agree with the verified mesh before its body is read.
Match generated STL and ZIP media types exactly after ignoring case and
semicolon-delimited parameters. Type names occurring only in parameters or
subtype suffixes must not authorize a body read. Recognize HTML catalog fallback
responses regardless of case, cancel them without reading and allow retrying.
Bound failed-response bodies separately, retain short readable service errors,
and show retry guidance for malformed, oversized, empty or interrupted errors.
Stop and deadline recovery must also cancel error-body reads while preserving
verified dimensions and discarding late failures after newer requests.
Once failure headers arrive, report that service details are being read and
bound that optional wait to five seconds. Return retry controls without aborting
the request signal needed for subsequent actions. Stopped file and error reads
must settle and release their readers even if the transport ignores cancellation.
Let visitors retry a loading or unavailable original catalog mesh without a CAD
build. Reload its static asset, cancel superseded or unused failed responses,
and preserve raw inputs, browser history, field errors, file confirmation and
relevant rejected-link explanations. Late original responses cannot replace
newer custom builds or models. Hide the action once a mesh is verified and keep
keyboard focus reachable without moving focus from a newer field edit. Image
fallback instructions must match the available viewer controls.
Let visitors revert unapplied or invalid edits to the last verified preview's
parameters without rebuilding or discarding its files. Retain list order and
cached CAD kits, update the shared URL and history, and disable the action during
a build or export. Reset must continue to restore the model's original defaults.
Recover the most recent editor's field values after a refresh in the same tab,
including decimal measurements, blank number fields and invalid list text.
Bound the record to 16 KiB of UTF-8 JSON and match its history entry, model and
complete field schema before applying it. Keep invalid values subject to normal
field feedback and download guards. Imports, Reset/Revert, history and edits
during builds must update the current draft. Preserve shared-link feedback when
measurements still match their URL; explain recovery when newer edits override
the URL. Re-fetch and verify files after refresh and require explicit CAD builds
for custom measurements. If storage is unavailable, keep editing and verified
downloads working and point to saving valid dimensions as a file. Failed writes
must discard stale snapshots when storage allows removal.
Support saving measurements and loading the parameters.json format from CAD
downloads. Use millimeters, known models and fields, finite bounded numbers,
whole counts and ordered numeric lists. Save canonical assembly quantities.
Confirm valid file dimensions and move focus to their first field before the
original preview finishes. A missing or corrupt original preview must keep the
accepted measurements and allow building them. Late preview results must reflect
current edits and files without hiding newer errors or replacing newer builds.
Loading a file must preserve verified files until a new preview succeeds,
require explicit building for changed dimensions, and ignore late reads after
edits, model navigation, newer files, or a build. Bound local files to 16 KiB.
Give local reads a 15-second deadline and preserve current fields and verified
files when reading stalls. Older deadlines and late bytes must not change newer
selections, CAD progress or cached downloads. Save dimensions and Copy link must
supersede a pending import without changing the measurements used by the new
action. Sharing must clear obsolete import errors; completed file confirmations
must retain their normal behavior when no read is pending.
Keep Copy link feedback current through edits, imports, Reset/Revert and model
navigation. Serialize clipboard writes and retain only the latest queued request
so overlapping copies finish with the last requested link. Provide a page-URL
fallback for denied, missing or slow clipboard access without blocking editing
or replacing CAD progress. Preserve preview correspondence and download guards.
Apply the catalog's scalar field ranges and the service's finite-number,
integer-count and list limits consistently to editing, saved files and sharing.
Reject invalid files atomically. Invalid or unreadable shared dimensions must
show original measurements with an explanation and a usable original preview.
Preserve decimal precision and invalid in-tab drafts through history. Late link
feedback must respect subsequent edits, Reset and file selections. Geometry
relationships remain checked by the canonical builders when updating previews.
Show invalid measurements beside the affected field, associate their descriptions
with the input, and include list errors in native form validation. Blocked save
and sharing actions must focus and reveal the field that needs correction.
Failed imports must show their own visible feedback near Load dimensions without
marking valid current inputs as invalid. Clear obsolete feedback through edits,
Reset/Revert, successful imports, new actions and navigation. Late file reads
must not restore dismissed errors. Preserve active CAD progress when sharing
invalid edits, and bound/wrap unknown-field diagnostics on small screens.
Allow a printer build-volume check using X, Y and Z extents measured from the
verified STL. Compare in the saved print orientation, allowing only a 90-degree
turn on the bed, and identify results that apply to the last preview while edits
remain unbuilt. Never infer a fit from an unverified mesh or reference assembly;
direct assemblies to their printable components. Keep finite positive printer
settings separate from model parameters, CAD progress, history and downloads.
Remember valid settings when browser storage allows it, and keep the check usable
when storage is malformed or unavailable. Provide an accessible Clear action
and explain that slicer brims and printer clearances require room.
Let visitors save up to twenty named dimension versions in this browser and
reopen them across parts and assemblies. Validate names and all stored parameters
against the current catalog, retain fine decimals and list order, and derive
assembly quantities from canonical inventory. Preserve ordinary preview/download
guards: unbuilt versions need Update preview, while matching versions can reuse
verified meshes and cached CAD. Removing a version must keep current fields and
files. Bound storage, reject same-model duplicate names, read current records on
each action, and preserve saved data on corrupt reads or failed writes. Offer the
portable Save dimensions flow for storage failures. Named actions must supersede
older file imports, keep late preview feedback current, and stay disabled during
CAD work. Review desktop/mobile controls and keyboard focus.
Provide a portable JSON backup for the complete named-version library, including
names, millimeter parameters and canonical assembly quantities. Validate its
format version, all model schemas and UTF-8 byte size before merging. Preserve
current entries and identities, assign new local identities to imported entries,
number conflicting names and skip repeated imports. Capacity, malformed records
and storage failures must reject atomically. Importing a library must keep editor
fields, preview correspondence, cached CAD and dimensions-file feedback. Bound
local reads to fifteen seconds, supersede them through newer named actions and
file selections, and discard late results after navigation, close or CAD work.
Keep backup controls disabled during CAD work and review keyboard/mobile use.

Allow renaming a selected saved version and replacing its dimensions without
removing and recreating it. Retain its identity, name on replacement, order and
other entries; use current storage and enforce existing name/schema limits.
Replacement must use validated measurements of the open model and work in a full
library. Avoid writes for unchanged edits. Keep current editor fields, history,
verified mesh and cached CAD; unbuilt measurements still require Update preview.
Preserve data on missing entries, malformed storage and failed reads/writes.
Supersede pending backup imports through either edit, cancel pending dimensions
reads on replacement, and keep unrelated file feedback when renaming. Use the
updated name if an opened version’s original preview arrives later. Disable both
controls during CAD work and review keyboard/mobile layouts.
