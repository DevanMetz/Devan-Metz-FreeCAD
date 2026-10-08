# Changes completed in this thread

Created the original **Everyday Prints** collection: **47 parametric print
files and six reference assemblies**, under Apache-2.0. The final addition
is a modular drawer-divider joint supporting cross, T, corner, and straight
layouts. Its reference boards seat against individual floors and hub backstops.

Every print file includes editable build123d Python source, STEP, STL, and
geometry-only 3MF. All dimensions are millimeters, and the supplied print
orientations put the bed face at Z=0. Sources validate supported inputs and
calculate derived dimensions. Six shared helpers keep matching parts consistent.

The latest local customizer and download build passes **233 focused browser
checks across nineteen suites**, the **53-model catalog and image smoke test**,
**50 unit tests**, TypeScript checks and the production build. File chunks are
copied immediately, preserving exact STL and CAD downloads when a transport
reuses its buffers. These changes are included in the collection archive.
The latest measurements can recover after a refresh in the same tab, including
invalid drafts, while custom downloads still require a verified matching preview.
Customized browser STL and CAD/kit filenames include verified preview dimensions
and a short hash of the downloaded file, including variants with the same outer size.
Keyboard focus now survives preview and CAD requests, Stop, failures and deadlines
without moving away from a field the user has chosen to edit.
Unavailable model links explain the problem and recover to normal library history
without applying their dimensions to a replacement model.
Parameter hints now explain declared ranges, whole-number rules, and numeric-list
limits before editing, with accessible descriptions and reviewed mobile layouts.
The transfer verifier now waits for the current request's reader and always
resumes its virtual clock after the five-second error-boundary check, preventing
an earlier reader or failed assertion from stalling later checks.
Browser graphics loss now shows the original catalog image while preserving
verified mesh dimensions, files, edits and pending requests. Graphics restoration
redraws the current mesh with the same camera and edge display, including after
model navigation or builds completed during the interruption. Five additional
checks use real WebGL loss and restoration with exported CAD fixtures; mobile
fallback and restored previews were visually reviewed.
Catalog loading now bounds actual received bytes to 2 MiB and enforces the
15-second deadline across headers and body reads, even when cancellation stalls.
Expired replies cannot publish cards or unlock a newer retry; searches, filters
and shared dimensions remain available for recovery. Six additional browser
checks cover stalled bodies, late headers, oversized transfers, the exact size
boundary with a UTF-8 BOM, split Unicode in reused buffers, and invalid UTF-8.
The catalog report records fourteen passing checks, with before-fix evidence
and a reviewed mobile retry layout under `review/cloud_catalog_transfer_*`.

## Complete design inventory

Each name below is the basename of its source and exported files. The
[collection guide](README.md) links every file and gives dimensions and use instructions.

| Use | New print files |
|---|---|
| Organization and displays — 11 | `parts_tray`, `divider_foot`, `divider_fit_coupon`, `divider_joint`, `phone_stand`, `label_stand`, `sliding_box`, `sliding_lid`, `sliding_fit_channel`, `sliding_fit_slider`, `bookend` |
| Cable handling, clips, and hardware — 11 | `cable_comb`, `cable_winder`, `cable_grommet`, `utility_peg`, `tie_anchor`, `fold_clip`, `cord_clip`, `hand_knob`, `slotted_shim`, `roll_adapter`, `corner_cable_guide` |
| Workshop layout aids — 8 | `corner_square`, `handle_marking_jig`, `radius_template`, `center_finder`, `round_stock_cradle`, `marking_saddle`, `ruler_stop`, `ruler_wedge` |
| Workshop handling, finishing, and sorting — 11 | `paint_pyramid`, `hex_bit_rack`, `hex_bit_fit_coupon`, `sanding_block`, `sanding_wedge`, `brush_rest`, `workshop_funnel`, `workshop_scoop`, `strap_corner`, `sorting_sieve`, `sieve_aperture_coupon` |
| Household use and labeling — 4 | `tube_squeezer`, `soap_dish_tray`, `soap_dish_insert`, `plant_marker` |
| Measured tube adapters — 2 | `tube_reducer`, `socket_fit_ring` |

## Reference assemblies

Added separate-component STEP references for the soap dish, sanding block,
sliding box, ruler stop, strap clamp, and divider joint. Assemblies use rigid
joint datums. Gray rulers, frames, and boards and the orange strap loop are
illustrative hardware, not extra print files. Print each assembly's constituent
parts separately. The tube reducer also has a labeled axial section in SVG
and PNG, generated from its source dimensions.

Fit samples cover divider boards, hex-bit shanks, sliding guides, tube sockets,
and sieve apertures. Instructions distinguish total clearance, per-side gap,
normal slot width, and diametral clearance where each applies.

## Build and export tools

- `export_design.py` rebuilds a selected part with repeated `--set NAME=JSON`
  overrides and a chosen output folder. It writes STEP/STL/3MF and a parameter
  record using build123d. Reference assemblies additionally need cadgen and
  export STEP only.
- `build_collection.py` generates explicit STEP sources, CAD facts, plane and
  positioning information, solid-validity reports, print meshes, and four views
  per model. It can rebuild selected designs or the whole collection.
- `validate_designs.py` checks intended dimensions and features, alternate sizes,
  invalid inputs, virtual component fit, independent volumes where applicable,
  and the delivered STL/3MF meshes.
- `verify_portable_export.py` tests the public exporter from copied source-only
  files, checks STEP round trips and meshes, and rejects unknown parameters.
- `make_preview.py` creates labeled review sheets, the collection overview,
  and stable documentation images. Saved view lookup works after copying or
  unzipping the collection.
- `make_index.py` builds a searchable offline image gallery and Markdown image
  index for all 53 prints and references, with categories, dimensions, file
  links, and four saved CAD views per model. Preview rebuilds also refresh it.
- `package_collection.py` rejects geometry changed after validation, writes
  SHA-256 manifests, and verifies archive CRCs and every packaged file's hash.
- `make_reducer_section.py` generates the tube-reducer section drawing.

## Design corrections and verification

During review, corrected the tray's rounded-corner wall thickness, opened both
ends of the divider coupon slots, reduced the tube-squeezer entry slope, fixed
an unintended ledge in the utility peg, corrected the plant-marker stake's
extrusion direction, refined mesh export accuracy, and simplified the sieve
handle root to remove tiny Boolean faces. Matching sets were checked in their
working orientation, including wedge engagement, soap drainage space, captured
sliding guides, tube seating stops, strap guide gaps, and divider board contacts.

The final [geometry report](review/design_validation.json) covers **142 printable
parameter configurations plus 30 assembly/fit configurations: 172 total**.
All **94 default STL/3MF exports** have one connected, watertight, consistently
wound, positive-volume body on the bed. Mesh dimensions match their source
solids within 0.01 mm and volumes within 0.1%. The mesh scan found no downward
faces above the bed steeper than 45 degrees from vertical in the supplied
orientations; this does not replace slicer review.

The [portable-export report](review/portable_export_validation.json) covers
**17 cases: twelve customized parts and five assemblies**. Four CAD review
views are included for every print and reference assembly, with written
[visual-review notes](review/VISUAL_REVIEW.md).

## Documentation and local environment

Added the collection guide, CAD brief, printing and customization instructions,
LICENSE/NOTICE, pinned dependencies, review evidence, previews, manifests, and
the complete [download archive](everyday-prints.zip). Updated the repository
README to introduce and link the collection. Added local CAD environment,
browser-cache, generated-CAD-cache, and Python-cache entries to `.gitignore`.

Set up an isolated `.venv-cad` runtime and cached snapshot browser. A venv-only
workaround skips malformed Windows font files; no system fonts were modified,
and the designs use no text outlines. Started and checked the included CAD
Viewer server and saved local review links. The in-app browser blocked that
localhost viewer, so saved CAD snapshots provide the visual review. Details
and reproducibility limits are recorded in [BUILD_ENVIRONMENT.md](review/BUILD_ENVIRONMENT.md).

These are CAD-validated prototypes. **No physical prints have been tested.**
Printed fit, strength, retention, accuracy, liquid sealing, fatigue, and service
performance still need trials with the user's printer and materials. The Cloudflare app below was
deployed publicly at the user's request.

## Hosted, customizable library

Added [the public Cloudflare Worker](https://everyday-prints.metzdevan.workers.dev)
and [its source and deployment guide](cloud/README.md), using the new `cf` CLI.
The responsive gallery includes every model, saved CAD images, fuzzy/prefix
search, category/type filters, and original files. Its browser editor exposes the
canonical scalar and list parameters, renders STL meshes with orbit/zoom and
standard views, carries shared dimensions from assemblies to printable parts,
and supports links containing custom measurements.

The Worker delegates real CAD regeneration to a Cloudflare Container running the
original Python builders. Customized previews and downloads use the same mesh;
the browser verifies its SHA-256 and disables download when edits are unapplied.
Builds have validated input types and sizes, original dimension guards, geometry
checks, isolated processes, time limits, per-IP rate limits, and one compute slot.
The runtime uses a saved filesystem snapshot and shuts down after idle time.

Local HTTP verification passed all 47 printable defaults, five customized parts,
two assembly references, and seven invalid-input cases. Browser checks covered all
53 catalog images, fuzzy search, custom geometry, matching downloads, invalid
geometry, assembly navigation, share links, and mobile layout. Current evidence is
in `review/cloud_runtime_validation.json` and `review/cloud_ui_validation.json`.

Production smoke tests also passed customized dimensions, numeric lists,
selectable divider topology, transferred mesh hashes, watertight solids, and
rejection of unknown models/keys and invalid numeric inputs. The hosted Worker
uses native Container execution directly, with no background HTTP service.
The browser tests also passed against the deployed public site with its Content
Security Policy enforced. Dependency audit reports zero vulnerabilities.
See `review/cloud_live_validation.json`. The collection ZIP includes the cloud
application source and deployment instructions; generated duplicates and local
dependencies are excluded.

## Development continuation — October 1, 2026

Hardened the browser preview and sharing flows. Original meshes now use the same
SHA-256 verification as custom builds. Returned model names, dimensions, units,
and applied parameters are checked before accepting a preview. A delayed original
load cannot replace a completed custom build, and model switches share one viewer
initialization. Edits made during a build keep stale downloads disabled and show
the appropriate update or invalid-input message. Clipboard denial leaves a usable
page URL containing the current dimensions; late clipboard results cannot change
another model's status. Devices without WebGL show a clearly labeled original
catalog image while keeping verified custom STL downloads available.

Extracted bounded request reading and parameter validation into
`cloud/src/request.ts`. Null parameter objects are rejected before invoking the
CAD runtime. Integer fields come from the canonical Python parameter types in
the prepared manifest, replacing the Worker's duplicate field-name list.

The [browser-state report](review/cloud_ui_state_validation.json) records nine
passing regression checks using a real custom CAD mesh with controlled response
delays and failures. The [request tests](cloud/tests/request.test.ts) pass eight
checks covering the complete catalog, input types, bounded streamed requests,
cancellation, and split UTF-8. The existing browser smoke test, TypeScript check,
and production build also pass locally. The collection packager includes the
new request helper and tests. These follow-up changes have not been deployed.

### Catalog loading and recovery

Added a loading state and an in-page Try again action with a 15-second deadline
for stalled catalog requests. Searches and type filters entered before the
catalog arrives no longer raise browser errors. Retry keeps those filters and
any shared model dimensions. Catalog validation checks dimensions, parameter
metadata, unique names, and component references before publishing the library.
Print/assembly counts come from the loaded catalog, and the result count,
loading state, and errors have accessible announcements.

The [catalog report](review/cloud_catalog_validation.json) records fourteen passing
browser checks for delayed loading, failure/retry, broken connections, malformed
responses, shared links, mobile layout, dynamic counts, stalled requests, late
responses, byte limits, split Unicode, and invalid UTF-8.
The existing nine preview-state checks and the full browser smoke test continue
to pass. The production build and refreshed collection archive include these
local changes.

### Browser navigation and draft restoration

Opening a model now adds a browser history entry. Back and Forward restore the
library's filters and focus, raw dimension edits (including invalid drafts),
and recent verified previews. Assembly-to-component navigation preserves each
editor's dimensions. Closing a nested component returns to the library; closing
a direct model link opens the library on the same site. Late build responses
cannot replace the editor reached through browser navigation.

The preview cache is limited to 32 MiB per tab and 64 saved views. Cached meshes
pass the same hash and metadata checks when restored, and downloads stay
disabled for unapplied edits. Reloads and shared links retain valid dimensions
but require a new preview before downloading a custom mesh.

The [navigation report](review/cloud_navigation_validation.json) records nine
passing browser checks. The existing preview-state, catalog-recovery, and full
browser smoke checks also pass. The production build and refreshed archive
include these local changes; they have not been deployed.

### Customized editable CAD downloads

Added Download CAD files to the model editor. Its ZIP contains a STEP solid with
the current preview dimensions, saved parameters, canonical sources and shared
helpers, licensing, checksums, pinned CAD dependencies, and a standalone rebuild
script. Printable parts also include the preview's exact STL and a 3MF using the
same tessellation in millimeters. Reference assemblies also offer Download
parts kit: a reference STEP plus STEP, STL, and 3MF for every printable component
in its canonical bed orientation. Changing `parameters.json` and running the
included script rebuilds the model and its kit components at those dimensions,
applying shared assembly parameters while retaining component-specific defaults.
Rebuilt parameter files retain the kit inventory, print quantities, and
fit-coupon labels. The customizer accepts fine continuous dimensions such as
180.55 mm while still requiring whole numbers for counts.

Original catalog meshes use a different tessellation from live CAD builds, so
the first CAD download refreshes an original preview before exporting. Downloads
verify the ZIP checksum and preview correspondence. Invalid or unapplied edits
disable both download actions; edits and navigation during an export discard its
obsolete result. Builds retain the existing rate limit and 90-second isolated
job deadline, with an 8 MiB response and 24 MiB uncompressed package limit.
Repeated CAD and kit downloads reuse one verified ZIP while the preview stays
the same. A new preview, model switch, or editor close clears this cache.
Revert edits returns the form to the last verified preview's dimensions without
rebuilding. It restores invalid scalars and ordered numeric lists, retains the
preview and any cached CAD kit, and updates the shared URL and saved history.
The action appears for unapplied edits once a verified preview exists and is
disabled during a build or export. Reset continues to restore original defaults.
The [revert report](review/cloud_revert_validation.json) records nine checks for
file reuse, lists, defaults, waiting/stopping races, missing previews, history,
shared assembly dimensions and kits, and mobile keyboard use. Focus returns to
the first parameter after reverting; the parameter actions have 44 px touch
targets and the mobile layout was visually reviewed.
Saved dimensions adds file controls above the form. Save dimensions exports
the current measurements as millimeter JSON, including canonical assembly kit
quantities, without building CAD. Load dimensions accepts those files and
parameters.json from a CAD ZIP, opens the named model, and restores ordered
lists and scalar values. Partial files use known defaults. Unknown models and
fields, wrong units and numeric types, fractional counts and excessive values
are rejected. Files are capped at 16 KiB before reading and after UTF-8 decoding.
Rejected files preserve the draft, preview and cached download. New edits,
navigation, newer file selections and builds discard late reads. Changed
dimensions require Update preview; matching dimensions reuse verified files.
The [saved dimensions report](review/cloud_dimensions_validation.json) records
eleven browser checks with real CAD metadata, actual file choosers, cached ZIPs,
kit inventories, error recovery, late reads and mobile keyboard controls.
Twelve parameter and file-validation tests cover all 53 defaults and field
ranges, lists, counts, numeric types and caps, units, byte limits, Windows UTF-8
BOMs and canonical inventories. The mobile layout was
visually reviewed.
Edit events, Reset and Revert invalidate pending file reads even when the final
field values return to their starting values; that race was reproduced and fixed.
Copy link now reports separately from CAD progress. Its clipboard queue runs one
write at a time and retains only the latest pending request. Two races were
reproduced and fixed: stale feedback after edits, and older writes overwriting
the latest requested URL. Edits, Reset, Revert, file imports and navigation
clear sharing feedback. After three seconds without a result, the current page
URL is offered as a fallback; the editor remains usable. Denied or missing
clipboard access provides the same fallback. Pending copies cannot replace
build messages or unlock stale downloads.
The [sharing report](review/cloud_share_validation.json) records ten checks for
these cases, including returned edits, queued writes after denial, model changes,
copying during a build, and mobile keyboard use. Five queue tests verify ordering,
bounded pending requests and error recovery. Waiting and mobile layouts were
visually reviewed.

The parameter validator is now shared by editing, saving, importing and sharing.
The browser previously called a 251 mm tray valid for saving and sharing despite
its 250 mm field limit, and allowed shared values exceeding the service's numeric
cap. These mismatches were reproduced and fixed. JSON numeric strings, unknown
keys, fractional counts and invalid lists are rejected without partly applying
parameters. Invalid or unreadable links show the model's original dimensions
with an explanation and discard the rejected URL parameters. History retains
invalid in-tab drafts; Revert restores verified files without rebuilding. A late
original preview cannot restore outdated link feedback after edits or Reset.
The [parameter browser report](review/cloud_parameters_validation.json) records
nine checks for these cases, valid fine decimals and list order, retained CAD
cache, and mobile keyboard recovery. The mobile error layout was visually
reviewed. Geometry sources are unchanged.

Validation failures now identify their field and show an associated message
beside its input. Save dimensions and Copy link focus and reveal the invalid
field. A mobile failure was reproduced: Save previously left focus on its button
while the error was below the viewport. Numeric-list errors now participate in
native form validation. Corrected values, Reset and Revert clear invalid states.
Failed imports have separate, visible feedback beside Load dimensions; valid
current measurements and verified downloads remain available. Long unknown
parameter names are abbreviated, and error text wraps. File reads invalidated by
edits, Reset, new selections or navigation cannot restore old errors. Invalid
sharing during a build keeps CAD progress and Stop waiting intact. The
[field feedback report](review/cloud_field_feedback_validation.json) records
eleven checks for these cases, history restoration and mobile keyboard recovery.
The mobile field and file-error layouts were reviewed, and the close control
remains reachable after automatic scrolling.
Stop waiting restores the editor during a stalled preview or CAD download while
retaining the last verified preview and current edits. A 15-minute browser
waiting deadline also recovers automatically. The service may still finish the
request. Late results cannot overwrite a new preview, download an obsolete ZIP,
or unlock a newer retry.

The [build recovery report](review/cloud_build_recovery_validation.json) records
ten passing browser checks with real CAD fixtures and virtual time. They cover
stalled headers and bodies, cancellation, deadlines, retries, old deadlines,
late service errors, navigation, invalid drafts, missing previews, and the mobile
stop control using a keyboard. The mobile waiting layout was visually reviewed.
Verified files now become ready independently of the optional 3D viewer. Its
loading state shows a labeled original catalog image and the current mesh
dimensions. Late initialization displays the current verified mesh without
discarding a CAD download cache. Script or graphics failures leave the verified
files available; a closed editor does not create an unused renderer.

The [viewer loading report](review/cloud_viewer_loading_validation.json) records
eight passing checks for delayed modules, STL/CAD downloads, late upgrades,
navigation, closed editors, missing WebGL, rendering failures, and corrupt
meshes. The real renderer's cleanup was exercised and the loading-image layout
was visually reviewed.

Original previews, rebuilt STLs, and CAD ZIPs now use a bounded streamed reader.
It cancels transfers over 8 MiB using actual incoming bytes, independent of the
response's stated size. Interrupted and empty transfers show a retryable error
and keep the last verified preview; Stop waiting cancels a pending read.
Captured request signals prevent late bytes from joining a newer build.
The [transfer report](review/cloud_transfer_validation.json) records eight
browser checks for these failures, recovery, chunked file integrity, and the
largest original STL. Eight reader tests cover byte boundaries, cancellation,
empty bodies, late bytes, and a cancellation promise that never finishes.

The [export report](review/cloud_export_validation.json) records ten real CAD
downloads and source rebuilds, including all six assembly kits, six rejected
inputs, edited saved part and assembly parameters, and the native Container
output contract. STEP validity, positive solid volumes, bounds, STL/3MF
consistency and units, component bed placement, kit quantities, and archive
hashes passed. Each component is exported once with its required print quantity
recorded in the inventory.
The [CAD inspection report](review/cloud_export_cad_inspection.json) records facts,
planes, positioning, and geometry validation for all 22 exported STEP samples
and kit components. Every inspection fingerprint matches its current STEP file.
The reusable inspection verifier refreshes stale render artifacts and can resume
completed checks when their STEP fingerprints still match.
An isometric snapshot of the fitted tray was reviewed; canonical geometry was
unchanged by this export workflow, so the other existing model snapshots apply.

The [export browser report](review/cloud_export_ui_validation.json) records fourteen
passing checks, including a real 180.55 mm custom download, whole-number counts,
original preview refresh, verified ZIP reuse and cache invalidation,
stale edits, model switches, transfer corruption, incorrect metadata, service
recovery, reference assemblies, kit quantities and fit coupons, malformed kit
inventories and catalogs, mobile layout, no WebGL, and a reachable close control
after scrolling long forms. The editor keeps its header visible while the preview
and parameter form scroll beneath it. The compiled app passes 233 focused browser
checks across nineteen suites, plus the full 53-model catalog and image smoke test.
The TypeScript check, fifty request/transfer/dimension/clipboard/error tests,
and production build pass. The native
runtime report records 54 successful mesh jobs and seven rejected inputs.

The kit inventory follows the canonical assembly sources:

| Reference assembly | Printable kit |
| --- | --- |
| Soap dish | One tray and one insert |
| Sanding block | One block and two wedges |
| Sliding box | One box, one lid, and two labeled fit coupons |
| Ruler stop | One stop and one wedge |
| Strap clamp | Four corner pads |
| Divider joint | One joint |

Reference rulers, frames, straps, and boards are excluded from print files.
Sliding-box fit coupons should be printed and tested before the full parts.
These are export and browser changes; the canonical geometry sources remain
unchanged, so their existing reviewed CAD snapshots apply.

Windows loopback networking is unavailable in this resumed environment. The
runtime and export verifiers now accept `--native`; all fourteen browser verifiers
accept `--offline`, serving the compiled production assets through local
Playwright routes at a secure `.test` origin and running real native CAD jobs.
These checks cover runtime and browser behavior without claiming verification
of the Worker's HTTP routing or rate limiter. The test helper uses workspace
temporary directories so Lib3MF can write under restricted Windows accounts.
These changes are local and have not been deployed.

Loading a valid file for another model now confirms the dimensions and focuses
its first field before the original mesh transfer completes. Missing or corrupt
original previews retain that confirmation and leave Update preview available.
Downloads remain tied to verified meshes matching the current inputs. Late
original previews reflect Reset and newer valid files while preserving newer
field/file errors and discarding results after builds or model switches.
The [dimensions-preview report](review/cloud_dimensions_preview_validation.json)
records twelve checks, including exact STL and CAD ZIP downloads rebuilt from
loaded parameters when the original preview is unavailable. The
[mobile review](review/cloud_dimensions_preview_mobile.png) shows the accepted
dimensions and unavailable-preview feedback.

Malformed failed-response JSON previously exposed a JavaScript diagnostic for
both preview builds and CAD downloads. These paths now read at most 16 KiB,
preserve short service messages and provide readable retry instructions for
invalid JSON or UTF-8, unexpected values, oversized, empty and interrupted error
bodies. Stop and a five-second diagnostic deadline cancel stalled error reads, and late
bytes cannot overwrite newer results. The shared file reader keeps its 8 MiB
limit for actual model files. Eight new unit checks and seven additions to the
[transfer browser report](review/cloud_transfer_validation.json) cover these
cases, including split UTF-8, exact STL/CAD retries and the
[mobile stopped-error review](review/cloud_error_response_mobile.png).

Failure headers previously left the editor displaying build progress while it
waited up to the full CAD deadline for diagnostics. The editor now reports that
the request failed and it is reading details. Missing details restore retry
controls after five seconds, while details arriving within the limit remain
readable. The original request signal stays usable. Pending file reads now settle
and release their readers immediately on cancellation even when a transport
ignores it. The existing 15-minute limit for actual builds still passes its
recovery checks. Two additional unit checks and three more transfer browser cases
verify the short deadline, reader release, useful delayed details, and exact
downloads after a retry, including recovery before the first verified preview. The
[mobile failure review](review/cloud_error_wait_mobile.png) shows the restored
download controls and preserved dimensions after the short wait.

The installed CAD Viewer npm launcher is missing. Its bundled Python server
started, but the resumed session's loopback connections were denied or timed out,
so a live review link could not be verified. The fitted STEP sample and reviewed
snapshot remain available under `review/`; the failed-access evidence is recorded
in `review/cloud_export_viewer_validation.json`.

Original catalog meshes now have Retry original preview while loading or
unavailable. It reloads the static asset without a CAD job, resetting inputs or
adding a history entry. Superseded transfers and unused failed bodies are
cancelled without waiting for cancellation to finish. Raw invalid drafts,
ordered lists, accepted-file confirmation, rejected-file feedback and relevant
shared-link explanations survive recovery. Late responses cannot replace newer
models or custom builds. The action hides after verification and returns focus
to the first field only when it was still focused. The fallback image now has
accurate viewer instructions. Eighteen compiled-browser checks cover these
cases, repeated failures and retries, original STL verification, cached CAD
reuse, assembly restrictions and mobile keyboard focus. The baseline, report
and reviewed mobile image are saved under `review/cloud_original_retry_*`.

Preview details are now validated before reading the file. Invalid models,
units, parameters, bounds, formats, hashes and preview file types return retry
controls immediately instead of waiting for an unusable body. CAD responses
also validate archive hashes before transfer. Rejected or obsolete responses
cancel their unused bodies without waiting for cancellation, preserving newer
Stop messages, requests, previews, measurements and verified downloads. First
preview failures and Stop now keep accurate image hints and invalid-field
status. Eight new checks bring the transfer suite to twenty-six, covering
stalled success bodies with invalid details, nonresponsive cancellation, late
headers after Stop or model navigation, overlapping CAD retries and mobile
invalid drafts. The baseline and reviewed mobile image are saved as
`review/cloud_response_discard_baseline.json` and
`review/cloud_response_discard_mobile.png`; results are included in the transfer
report. All 179 focused browser checks, the 53-model smoke test, forty-seven unit
tests, TypeScript check and production build pass. Canonical geometry and all
twenty-two reviewed STEP exports match their recorded hashes.

The editor now separates CAD building, receiving files and verifying them.
Original previews, rebuilt meshes and CAD ZIPs show the actual received-byte
count in B, KiB or MiB, independently of saved-dimension and error messages.
It does not trust the stated response size or invent a completion percentage.
Build reminders stop when valid file receipt starts; complete files show a
verification phase before downloads become available. Stop, deadlines, errors,
completion and model navigation clear the status. Late bytes and old requests
cannot update or hide a newer transfer. Fifteen new compiled-browser checks
cover stalled receipt, delayed verification, saved and rejected files, retries,
model switches, build reminders, deadline recovery, service details, stale
edits, exact downloads, cached CAD reuse and mobile keyboard Stop. Three new
unit checks cover actual byte counts, size limits before progress and late
bytes after Stop. All 179 browser checks across fifteen suites, the 53-model
smoke test, forty-seven unit tests, TypeScript check and production build pass.
The baseline, report and reviewed mobile image are saved as
`review/cloud_transfer_progress_*.json` and
`review/cloud_transfer_progress_mobile.png`. Canonical geometry and all
twenty-two reviewed STEP exports remain unchanged.

The streamed reader now copies every accepted chunk immediately into a growable
byte buffer. A baseline reproduced corrupted bytes when the transport reused
its backing buffer; the reader previously kept references until the transfer
ended. The new accumulator avoids retaining a list of fragments and clips its
capacity to the configured response limit, including the smaller service-error
limit. Empty chunks are ignored and completed buffers contain exactly the
accepted file length. Three new unit tests cover reused buffers, tiny borrowed
views, odd capacity limits and empty fragments. Five browser checks preserve
exact original/customized STL files, CAD ZIPs and split UTF-8 service details
under buffer reuse, and verify empty fragments before a valid file. The
five-second error test now pauses virtual time and checks both sides of the
deadline. All 184 focused browser checks, the 53-model smoke test, 50 unit tests,
TypeScript checks and production build pass. The baseline is saved as
`review/cloud_chunk_buffer_baseline.json`; current results are in
`review/cloud_transfer_validation.json`. Canonical geometry and all twenty-two
reviewed STEP exports match their recorded hashes.

Generated preview and CAD responses now match the actual media type, ignoring
case and semicolon-delimited parameters. The baseline reproduced stalled reads
for types mentioned only inside a parameter and immediate rejection of valid
mixed-case STL/ZIP headers. Misleading media types now cancel their unread bodies
and return retry controls; accepted variants still deliver exact verified files.
Original catalog responses also reject mixed-case HTML fallback pages before
reading them. Four transfer checks and one original-retry check cover these
paths, including subtype suffixes, combined type values, whitespace, parameter
values containing semicolons and fresh CAD exports. The progress verifier waits
for each newly opened stream and deliberately delays retry/CAD headers, removing
a race with an old reader's release handle. Virtual clocks are installed before
page scripts run. All 189 focused browser checks across fifteen suites, the
53-model smoke test, 50 unit tests, TypeScript checks and production build pass.
The baseline is saved as `review/cloud_media_type_baseline.json`; current results
are in the transfer, original-retry and progress reports. Canonical geometry and
all twenty-two reviewed STEP exports remain unchanged.

Unfinished measurements now recover after a refresh in the same browser tab.
The baseline reproduced lost decimals, blank number fields and invalid list
text, with the original model becoming downloadable instead. A single draft
stores the latest editor's field values, model and history-entry identity within
a 16 KiB UTF-8 limit. Compatible records restore fields without starting CAD work
or trusting geometry from storage. Original meshes are fetched and verified
again; changed or invalid inputs retain the existing download guards. Imports,
Reset/Revert, history and edits during pending builds update the current record.
Malformed or incompatible records are ignored; denied storage and failed writes
keep editing and downloads usable, with guidance to save a dimensions file.
Failed writes clear older snapshots when possible. Feedback distinguishes newer
recovered edits from measurements that still match a valid shared URL. Twelve
browser checks cover these paths, exact rebuilt STL/CAD files, UTF-8 limits,
quota failures, fresh tabs and mobile focus/layout. The baseline, report and
reviewed image are saved as `review/cloud_draft_refresh_baseline.json`,
`review/cloud_draft_recovery_validation.json` and
`review/cloud_draft_recovery_mobile.png`. All 201 focused browser checks across
sixteen suites, the 53-model smoke test, 50 unit tests, TypeScript checks and
production build pass. Canonical geometry and all twenty-two reviewed STEP
exports match their recorded hashes.

Customized browser STL and CAD/kit downloads now include the verified preview's
outer dimensions in millimeters, rounded to two decimals, and twelve characters
of the downloaded file's SHA-256. Two real decimal variants previously produced
the same filename despite different bytes. The new names distinguish those
variants and internal layout changes at the same outer size. Default names and
saved-dimensions filenames stay unchanged. Cached ZIPs retain their verified name
when edits are reverted. Five browser checks cover these paths, list-based model
dimensions, and exact STL/CAD correspondence. Evidence is saved in
`review/cloud_download_names_baseline.json` and
`review/cloud_download_names_validation.json`. All 206 focused browser checks
across seventeen suites, the 53-model smoke test, 50 unit tests, TypeScript checks
and production build pass. Canonical geometry and the twenty-two reviewed STEP
exports match their recorded hashes. These changes remain local.

Build and CAD controls no longer lose keyboard focus when disabled. The baseline
recorded focus on the page body after activation and after Stop waiting disappeared.
Focused controls now hand focus to Stop waiting. After completion, failure, Stop
or the fifteen-minute deadline, focus returns to the initiating control if it is
still available, otherwise Update preview. Field submission keeps its focus,
and moving to another field or leaving the editor prevents late focus restoration.
The queued restoration waits for download controls to be enabled and checks the
current request, model and dialog. It also covers the original preview refresh
before a CAD export. Nine browser checks verify keyboard activation, exact files,
cached ZIP reuse, both original CAD requests, failures, deadlines, field focus
and mobile navigation. Evidence is saved in
`review/cloud_keyboard_build_focus_baseline.json`,
`review/cloud_build_focus_validation.json` and
`review/cloud_build_focus_mobile.png`. All 215 focused browser checks across
eighteen suites, the 53-model smoke test, 50 unit tests, TypeScript checks and
production build pass. Canonical geometry and the twenty-two reviewed STEP
exports remain unchanged. The checkpoint remains local.

Unavailable model links now explain their recovery to the library. The baseline
showed a silent fallback, retained model/dimensions query parameters and an extra
history entry when a replacement editor was closed. After catalog validation,
unknown, empty and malformed model names show a bounded library notice. Their
model and dimensions parameters are removed with a history replacement, while
unrelated query data and the fragment remain. The recovered library has depth
zero, so filtered browsing and editor close use normal Back/Forward history.
Choosing a valid model clears the notice and uses its own defaults; valid custom
links retain their measurements. Catalog failures preserve the requested link
until a successful retry. Seven checks cover these paths, long identifiers,
older unavailable history entries with late builds, current search focus and a
mobile keyboard STL download. Evidence is saved in
`review/cloud_unavailable_link_baseline.json`,
`review/cloud_unavailable_link_validation.json` and
`review/cloud_unavailable_link_mobile.png`. All 222 focused browser checks across
nineteen suites, the 53-model smoke test, 50 unit tests, TypeScript checks and
production build pass. Canonical geometry and the twenty-two reviewed STEP
exports match their recorded hashes. These changes remain local.
