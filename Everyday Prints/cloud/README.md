# Everyday Prints on Cloudflare

Public library: **[everyday-prints.metzdevan.workers.dev](https://everyday-prints.metzdevan.workers.dev)**.

The site includes all 47 print files and six reference assemblies. Search supports
prefixes, minor spelling mistakes, categories, model types, and useful terms such
as “organizer,” “wire,” and “garden.” Every model exposes its canonical parameters.
Visitors can orbit/zoom a real STL preview, change measurements, rebuild, download
the same mesh they see, and share a URL containing their dimensions.

Assembly references have component links and pass shared dimensions to those
parts. Assemblies are not offered as single printable STLs. Original STEP, STL,
3MF, and Python source files remain available. All units are millimeters; physical
print testing remains pending.

The local editor also offers editable CAD downloads and printable assembly kits
with fitted components, quantities, and fit coupons. These development changes
have not been deployed to the public library; see `../THREAD_SUMMARY.md`.

## How it works

- A TypeScript Worker serves Vite static assets and validates `POST /api/generate`.
- Its SQLite Durable Object owns one Cloudflare Container. The Container runs the
  original build123d/OpenCASCADE Python builders; there is no browser-only rewrite
  or scaling of a precomputed mesh.
- The managed Debian image installs pinned build123d/cadgen dependencies on first
  use and saves a filesystem snapshot. Subsequent starts restore that snapshot
  and execute each CAD job directly through the native Container API without
  Internet access. A background HTTP server is not required in production.
- Each build runs in a separate Python process with a 90-second deadline. Source
  guards reject unsupported dimensions, and the result must have valid,
  positive-volume solids. Printable parts must be one solid on Z=0.
- Requests are limited to 16 KiB, known models/keys, finite numeric values, and
  lists of at most 16 entries. A public rate limiter permits 12 valid build
  requests per minute per IP. One build runs at a time; busy visitors get a
  retryable response. The Container stops after five minutes of inactivity.
- The browser checks every mesh's SHA-256 and model metadata before displaying
  it and enables download only when the inputs match that preview. Late previews
  cannot overwrite a newer model or build. No visitor CAD code executes.

Original previews and STL downloads are static and do not wake the CAD service.
Unavailable model links show a library notice after the catalog has been
validated. Their model and dimensions query parameters are removed with a
history replacement; unrelated query data and the URL fragment are preserved.
Empty and malformed model names follow the same recovery. Choosing another
model clears the notice and uses normal filtered-library Back/Forward history.
No CAD build starts, and valid model links retain their measurements. A catalog
failure keeps the original link available for retry before deciding whether its
model is present.

`verify_unavailable_links_ui.py` records seven browser checks for route recovery,
malformed identifiers, filtered history, catalog retry, valid links, late builds
from older history entries, and a mobile keyboard STL download. Results and the
mobile review are in `../review/cloud_unavailable_link_validation.json` and
`../review/cloud_unavailable_link_mobile.png`.

CAD and kit downloads run the builder with the saved dimensions. A first build
after inactivity includes Container startup time. The first installation
after changing the runtime bundle may take several minutes. Container usage is
billed to the account's existing Workers Paid plan.

The project uses the **new `cf` CLI** and `cloudflare.config.ts`. The
`enable_ctx_exports` flag provides a loopback namespace for `CadRuntime`, avoiding
a redundant external Worker binding. No local Docker daemon is needed for this
managed-image deployment.

## Build and deploy

From this directory, with a Python environment containing the parent collection's
CAD dependencies and Node/npm available:

```powershell
python prepare.py
npm ci
npm run typecheck
npm test
cf deploy --dry-run
cf deploy
```

`prepare.py` uses the parent collection's existing CAD screenshots, default meshes,
source parameters, and guide inventory. It creates `public/catalog.json`, asset
copies, and `src/generated/runtime.json`; these outputs are intentionally ignored
by Git. Rebuild and validate the parent collection before preparing changed CAD
sources. `package-lock.json` records the CLI, frontend, and build dependencies.

`cf auth login` is only needed on a machine without an authenticated account.
The Worker is named `everyday-prints` and its Container application is
`everyday-prints-cad`. Deploying the same project updates those resources.

## Local development and verification

Prepare the project first. In one terminal using the collection's CAD Python
environment, start the local HTTP bridge to the same CAD generator:

```powershell
python ../../.cad-cache/cloud-runtime/server.py 8086
```

In another terminal:

```powershell
npm run dev:local
```

Open `http://127.0.0.1:5178`. Vite proxies custom builds to the local Python bridge.
`cf dev` is also available for Worker development, but the CAD bridge is the
Docker-free local route for complete geometry testing.

```powershell
python verify_runtime.py
python verify_exports.py
python verify_ui.py
python verify_ui_state.py
python verify_catalog.py
python verify_navigation.py
python verify_export_ui.py
python verify_mesh_ui.py
python verify_build_recovery.py
python verify_viewer_loading.py
python verify_transfer_ui.py
python verify_transfer_progress_ui.py
python verify_revert_ui.py
python verify_dimensions_ui.py
python verify_import_actions_ui.py
python verify_dimensions_preview_ui.py
python verify_original_retry_ui.py
python verify_share_ui.py
python verify_parameters_ui.py
python verify_field_feedback_ui.py
python verify_live.py https://everyday-prints.metzdevan.workers.dev
python verify_ui.py https://everyday-prints.metzdevan.workers.dev
```

The browser checks require the parent collection's Playwright Chromium cache.
Reports and screenshots are saved under `../review/`. `verify_runtime.py` checks
all 47 printable defaults, five customized parts, two assemblies, mesh validity,
hashes, and rejected inputs. Production checks use a smaller set to stay below
the public rate limit. Production API and browser checks passed on the deployed
site; results are saved in `cloud_live_validation.json` and
`cloud_ui_validation.json`. Default and customized meshes passed watertightness,
volume, bounds, and transfer-hash checks.

`verify_ui_state.py` runs against the local development server. It generates one
real custom CAD mesh, then replays responses with controlled delays and failures.
Its nine browser checks cover late original previews, switching during viewer
initialization, edits during a build, corrupted meshes, mismatched metadata,
clipboard denial and late clipboard completion, and devices without WebGL.
Evidence is saved in `../review/cloud_ui_state_validation.json`. A fallback
catalog image is explicitly labeled as the original model; verified custom STL
downloads remain available. Copy-link fallback updates the page URL with the
current dimensions, including edits that have not been built yet.

Copy link reports its progress beneath the download controls, keeping CAD build
messages visible. Clipboard writes run one at a time and retain only the latest
queued request. Edits, Reset, Revert, file imports and navigation clear outdated
feedback. A copy taking more than three seconds offers the current page URL as
a fallback; editing and building remain available. Denied or unavailable
clipboard access also offers that URL, including unbuilt measurements.

`verify_share_ui.py` has ten checks for exact copied dimensions, rapid requests,
late results, returned edits, model changes, source-file imports, waiting and
denial recovery, invalid fields and mobile keyboard use. It also checks sharing
during a CAD build without replacing progress or unlocking downloads.
Results are in `../review/cloud_share_validation.json`.

Catalog loading has a 15-second deadline covering both headers and body reads,
including transports that ignore cancellation. Try again becomes available when
the deadline expires; old responses cannot publish cards or unlock a newer retry.
Unused bodies are cancelled without waiting for cancellation to finish.
The library accepts at most 2 MiB of actual received bytes, independently of
Content-Length, and rejects invalid UTF-8. Complete metadata and component
references are validated before any cards appear. Searches, filters and shared
model dimensions survive recovery, with accessible loading and error announcements.

`verify_catalog.py` records fourteen passing checks for delayed searches, HTTP
and connection failures, malformed catalogs, shared links, mobile recovery,
dynamic counts, stalled headers and bodies, late replies during retries,
oversized responses, the exact size boundary with a UTF-8 BOM, split Unicode
in reused chunk buffers, and invalid UTF-8. Results and before-fix evidence are
`../review/cloud_catalog_validation.json` and
`../review/cloud_catalog_transfer_baseline.json`; the reviewed mobile failure
state is `../review/cloud_catalog_transfer_mobile.png`.

`verify_navigation.py` checks Back and Forward through the library, assemblies,
and printable components, including unfinished and invalid dimension edits,
verified custom previews, late build responses, mobile dismissal, direct links,
and reloads. Nine passing checks are saved in
`../review/cloud_navigation_validation.json`. Navigation restores library
filters and focus. Closing a component returns to the library; closing a direct
model link opens the library on the same site. Recent previews are cached only
in the current tab, with a 32 MiB mesh budget and up to 64 saved views. Reloading
fetches and verifies the original mesh again; customized measurements require
Update preview before downloading their version.

The most recent editor draft is kept in this tab's session storage, bounded to
16 KiB of UTF-8 JSON. It contains the model name, history-entry identity and field
values. A refresh restores matching entries, including decimal measurements,
blank number fields and invalid or ordered list text. Records must match the
model's complete field schema; malformed, incompatible or oversized records are
ignored. The draft stores no meshes, CAD ZIPs or verification metadata, and
restoring it never starts a CAD build. Invalid values still show their field
errors and block saving, sharing and downloads.

Imports, Reset, Revert and edits during pending builds update the draft. History
navigation saves the current restored view; new views use their own entry
identity. Shared-link feedback remains when the fields match the validated URL,
while newer recovered measurements get their own explanation. A note explains
that Save dimensions keeps a portable file. If tab storage is unavailable or a
write exceeds the cap, the note directs the visitor to Save valid dimensions;
editing and verified downloads continue to work. Failed writes clear an older
snapshot when storage permits, preventing stale recovery.

`verify_draft_recovery_ui.py` has twelve compiled-browser checks for refreshes,
mobile layout and focus, invalid fields and lists, pending builds, exact rebuilt
STL/CAD files, Reset/Revert, imports across models, history, shared links and fresh
tabs, corrupt records, denied storage, UTF-8 byte limits and failed writes.
Its report and reviewed mobile image are
`../review/cloud_draft_recovery_validation.json` and
`../review/cloud_draft_recovery_mobile.png`.

Download CAD files builds a ZIP with the current preview dimensions. Printable
parts include STEP, STL, and 3MF. Download parts kit does the same for each
assembly's printable components in their canonical bed orientation, alongside
the reference STEP and a quantity list. Sanding kits need two wedges; strap
clamps need four corner pads; sliding boxes also include two labeled fit coupons.
Reference rulers, frames, straps, and boards are excluded from print files.
Each ZIP also includes saved parameters, canonical sources
and shared helpers, licensing, checksums, pinned CAD dependencies, and a
standalone `rebuild.py`. Extract the ZIP, install `requirements.txt` in a Python
virtual environment, and run `python rebuild.py`; changing the parameters object
in `parameters.json` changes the next rebuild. Shared assembly dimensions are
applied to each component; component-specific defaults remain in effect. Outputs
go to `rebuilt/`, with assembly components under `rebuilt/parts/<model>/`.
Rebuilt metadata retains the kit inventory, component quantities, and fit-coupon
labels. Continuous measurements accept finer decimals, such as 180.55 mm;
count fields still require whole numbers.

Inputs show their declared catalog bounds before editing, including millimeter
and degree units. Count fields identify whole numbers, and numeric lists explain
the one-to-sixteen entry limit and retained order. Each hint is connected to its
input's accessible description alongside field errors. Fields without declared
bounds point to related dimensions, whose relationships are checked by the
builder. The hints use the existing validation rules.
Rendered scalar, count, angle and list descriptions are recorded in
`../review/cloud_parameter_hints_review.json`; mobile reviews are
`../review/cloud_parameter_hints_mobile.png` and
`../review/cloud_parameter_hints_list_mobile.png`.

Original catalog STLs use a different tessellation from live builds. The first
CAD download refreshes an original preview before exporting, so the ZIP's STL
is the exact live preview mesh. After the first successful CAD or kit download,
the editor reuses its verified ZIP while the preview stays the same. The cache
holds at most one 8 MiB archive and clears on a new preview, model switch, or
editor close. The initial preview and export builds both count toward the public
rate limit. Unapplied or invalid edits disable downloads; edits or navigation
during an export cannot
trigger a download with obsolete dimensions. The browser verifies the ZIP's
transfer hash and its preview correspondence before saving it.

When a focused build or download control is disabled, keyboard focus moves to
Stop waiting. Completion, failure, Stop and the request deadline return focus to
the initiating control when it is available, or Update preview otherwise. Enter
in a measurement field keeps focus there during the build. Moving to another
field or leaving the editor preserves that newer focus; late replies cannot
restore focus to an old control. The original-preview refresh and subsequent
CAD export follow the same behavior.

`verify_build_focus_ui.py` records nine keyboard checks for completion and exact
files, Stop, field submission, cached CAD reuse, the two-request original CAD
path, service failures, deadlines, preserved field focus and mobile navigation.
Results are in `../review/cloud_build_focus_validation.json`; the mobile review
is `../review/cloud_build_focus_mobile.png`.

Customized browser STL and CAD/kit filenames include the verified preview's
outer dimensions in millimeters, rounded to two decimals, and the first twelve
characters of the downloaded file's SHA-256. For example, a custom STL is named
`parts_tray-custom-180.5x100x24mm-6f7e6198de7a.stl`. The fingerprint distinguishes
files with different internal geometry at the same outer size. Default model
names and saved-dimensions filenames remain unchanged; repeated cached downloads
retain the same name and bytes. The API's Content-Disposition names are unchanged.

`verify_download_names_ui.py` has five browser checks for default names, two real
decimal variants with exact STL/CAD correspondence, internal changes at the same
outer size, reverted edits and cached ZIP reuse, and list-based dimensions. It
records filenames and downloaded hashes in `../review/cloud_download_names_validation.json`.

Revert edits restores the form to the last verified preview's dimensions without
rebuilding or clearing its STL and cached CAD download. It restores invalid
fields and numeric lists in their saved order, then updates the shared URL and
browser history. The action appears when edits differ from a verified preview
and is disabled during a preview or CAD build. Stop waiting first to recover
from a pending request. Reset continues to restore the model's original defaults.
The parameter actions have 44 px touch targets; reverting returns keyboard focus
to the first field.

`verify_revert_ui.py` has nine checks for scalar/list recovery, verified file and
kit reuse, original defaults, stopping and late responses, missing previews,
history and shared URLs, assembly component dimensions, and mobile keyboard use.
It uses real CAD fixtures; results are in `../review/cloud_revert_validation.json`.

Open Saved dimensions above the parameter form to save or load measurements.
Save dimensions downloads `<model>-dimensions.json` with the current inputs,
millimeter units and canonical assembly kit quantities. It works before building
a preview. Extract a CAD ZIP to access its `parameters.json` file.
Load dimensions accepts that file or a saved dimensions file,
opens its model and fills the fields without starting CAD work. Partial parameter
objects use the model's defaults for omitted fields. Update preview is required
for changed dimensions; matching inputs retain the verified STL and cached ZIP.

Files are limited to 16 KiB. Model and parameter names, units, numeric types,
counts, list lengths and numeric bounds are validated before the form changes.
Local file reads also have a 15-second deadline. A stalled read shows retry
guidance beside Load dimensions and preserves the current fields and verified
downloads. Late file results and older deadlines cannot replace newer selections
or CAD progress. Save dimensions and Copy link supersede a pending import,
keeping the measurements used by the new action; Copy link also clears completed
import errors. Finished imports keep their existing confirmation and preview
behavior when no read is pending.

`verify_import_actions_ui.py` records seven browser checks for keyboard Save,
sharing while the clipboard waits, late invalid imports, both sides of the read
deadline, newer files and build progress, verified STL/CAD reuse, and mobile
timeout recovery. Current and before-fix evidence is in
`../review/cloud_import_actions_validation.json` and
`../review/cloud_import_actions_baseline.json`; the reviewed mobile state is
`../review/cloud_import_actions_mobile.png`.

Geometry and kit metadata supplied by the file cannot replace verified meshes or
the catalog's quantities. Rejected files preserve the draft and last preview.
Late reads after edits, navigation, newer selections or builds are discarded,
including edits returned to their starting values and Reset/Revert actions.
The controls are disabled during preview and CAD builds; mobile buttons have
44 px touch targets, and loading returns keyboard focus to the first parameter.

`verify_dimensions_ui.py` has eleven checks for real CAD metadata, saving unbuilt
decimal dimensions, verified file reuse, model/history restoration, lists,
canonical kits, malformed/oversized/unreadable files, late reads and mobile
file choosers and keyboard use. Results are in
`../review/cloud_dimensions_validation.json`.

A valid file confirms its loaded dimensions and focuses the first field before
the original preview finishes. Missing or corrupt original meshes keep that
confirmation visible and allow Update preview to build the saved version.
Downloads stay disabled until a verified mesh matches the current inputs.
Late original responses reflect Reset and newer valid files without dismissing
newer field or file errors, or replacing a custom build or another model.

`verify_dimensions_preview_ui.py` has twelve checks for these pending and failed
preview cases, mobile focus, saved values, exact rebuilt STL/CAD downloads,
newer file selections, Reset, and model switches. Its report and screenshot are
`../review/cloud_dimensions_preview_validation.json` and
`../review/cloud_dimensions_preview_mobile.png`.

Editing, saving, loading and sharing use the same catalog field ranges, whole
counts, finite values within -1000 to 1000, and lists of 1 to 16 numbers. Numeric
strings in JSON are rejected; continuous measurements accept fine decimals.
Invalid drafts cannot start builds, save dimensions or copy links.
Rejected imports preserve the current fields and verified downloads. Invalid,
malformed or oversized shared parameters show original dimensions with an
explanation and remove the rejected parameters from the URL. Later edits or
Reset prevent old link feedback from replacing the current form state. The
native builders still validate related dimensions and supported geometry.

`verify_parameters_ui.py` has nine checks for scalar ranges, integer counts,
list limits and types, atomic imports and cached CAD files, decimal and list
round trips, rejected and unreadable links, history restoration, mobile keyboard
recovery, and deferred original previews after edits and Reset. Its report and
mobile screenshot are `../review/cloud_parameters_validation.json` and
`../review/cloud_parameters_mobile.png`.

Invalid inputs have an associated message beside the field, an invalid state,
and native validation for both numbers and numeric lists. Blocked Save dimensions
or Copy link actions focus and reveal the first invalid field. Correcting it,
Reset and Revert clear the old feedback. An invalid copy during a CAD build
preserves its progress message and Stop waiting control.
Failed imports show visible feedback beside Load dimensions and preserve valid
current inputs and verified files. Edits, new file actions, Reset/Revert, builds
and navigation dismiss old file errors; late reads cannot restore them. Long
unknown parameter names are abbreviated and messages wrap on small screens.

`verify_field_feedback_ui.py` has eleven checks for offscreen mobile errors,
field focus and accessible descriptions, native list validation, corrections,
file/error ownership, long diagnostics, stale file reads, active build progress,
history restoration and keyboard recovery. Results are in
`../review/cloud_field_feedback_validation.json`; mobile screenshots are
`../review/cloud_field_feedback_mobile.png` and
`../review/cloud_dimensions_error_mobile.png`.

`verify_exports.py` checks ten real downloads, including scalar and list edits,
shared-helper parts, and all six assembly kits. It verifies STEP solid validity, bounds
and volume, STL/3MF watertightness and units, archive checksums, rebuilds from
extracted sources, edited saved part and assembly parameters, retained kit quantities,
component bed placement, rejected inputs, and the native Container output
contract. Samples go to `../review/cloud_export_samples/` and
the report to `../review/cloud_export_validation.json`.
`verify_cad_inspection.py` runs the installed CAD skill's facts, planes,
positioning, and solid-validation commands on all exported STEP files and kit
components, saving `../review/cloud_export_cad_inspection.json`; use `--inspect`
if that skill is installed outside the default `~/.codex/skills/cad` directory.
The verifier refreshes stale render artifacts and requires their fingerprints
to match the exported STEP. `--resume` preserves completed checks only when those
fingerprints still match.
Run the export verifier before
`verify_export_ui.py`, whose fourteen browser checks cover a real custom download
at 180.55 mm, whole-number counts, original-preview refresh, verified ZIP reuse,
cache invalidation, stale edits, navigation, corruption and mismatched metadata,
service recovery, reference assemblies, kit quantities and fit coupons,
malformed inventories and catalogs, mobile layout, no WebGL, and a reachable
close control after scrolling long desktop and mobile forms.
Its report is `../review/cloud_export_ui_validation.json`.

Retry original preview is available while the catalog mesh is loading or
unavailable. It reloads that static asset without starting a CAD build, changing
form inputs, or adding a history entry. Stalled requests are cancelled; unused
failed or superseded responses are also cancelled without waiting for their
bodies. Downloads still require a verified mesh matching the current inputs.
Retrying preserves invalid drafts, saved-file confirmation, rejected-file
feedback, and relevant shared-link explanations. Late original responses cannot
replace newer models, custom builds, edits, or errors. The retry disappears once
a mesh is verified, returning keyboard focus to the first measurement only if
the retry still has focus. Image fallback hints describe the unavailable viewer.

`verify_original_retry_ui.py` has nineteen browser checks for missing, HTML,
corrupt, oversized, stalled and repeated catalog transfers; exact raw drafts;
saved dimensions across models; rejected files and links; browser history;
newer edits, builds and navigation; verified CAD reuse; reference assemblies;
and mobile keyboard focus and touch target size. Mixed-case HTML responses must
also be cancelled before reading their stalled bodies. Its report and reviewed mobile
image are `../review/cloud_original_retry_ui_validation.json` and
`../review/cloud_original_retry_mobile.png`.

The browser reads original previews, rebuilt STLs, and CAD ZIPs as streams and
cancels the transfer when the received data exceeds 8 MiB. The limit counts
actual bytes even when the response's stated size is missing or incorrect.
Interrupted or empty transfers show a retryable error and retain the last
verified preview. Downloads still require matching dimensions and verified
hashes; incomplete files cannot become downloads.

Each nonempty chunk is copied immediately into an owned, growable byte buffer.
The reader does not retain a list of transport fragments, so reused buffers and
small views into larger buffers cannot alter accepted bytes. Its accumulator
capacity stops at the configured response limit. Empty chunks do not affect
progress or file contents, and returned files contain exactly the accepted bytes
without unused buffer capacity.

Failed preview and CAD responses also use a bounded stream reader. Error bodies
stop at 16 KiB, independent of the stated response size. Short service messages
are retained; malformed JSON, unexpected roots, non-string or oversized messages,
invalid UTF-8, empty bodies and interrupted transfers show a readable retry
message. Accepted messages are trimmed and limited to 512 characters. Once a
failure response arrives, the editor reports that it is reading service details
and waits at most five seconds for them. A slow body is cancelled and retry
controls return with the current preview and dimensions. Stop waiting also
releases pending readers immediately, including transports that ignore
cancellation; late bytes cannot replace newer progress, previews, or downloads.
The 15-minute deadline still applies while waiting for an actual CAD build.

Successful preview responses must identify the requested model, dimensions,
units, bounds, format, and a usable SHA-256 hash before their file is read. CAD
responses must also advertise a valid archive hash and the expected ZIP type.
Invalid details and file types are rejected immediately, even if the unused body
would stall. Unused responses are cancelled after rejected details, Stop, or
superseding requests; cleanup never waits for an unresponsive cancellation.
Complete files still pass the existing mesh/archive hash checks before becoming
downloads. Rejected responses preserve the current inputs and verified files.

Preview meshes also validate their binary STL facet count, exact record length,
finite normals and vertices, and positive extent on every axis. Measured bounds
must match the reported CAD dimensions within 0.05 mm plus one part per million
for single-precision coordinates. This covers the small tessellation differences
in the original catalog. Validation happens before replacing a verified preview
and works without the optional 3D viewer. CAD response dimensions are checked
against the verified mesh before reading an archive body.

`verify_mesh_ui.py` records six browser checks for inconsistent dimensions,
malformed facets with matching hashes, unavailable graphics, original-preview
recovery, rejected CAD details with an unresponsive body, cached downloads,
working retries, and mobile keyboard Revert/download actions. Evidence is in
`../review/cloud_mesh_dimensions_validation.json` and
`../review/cloud_mesh_dimensions_baseline.json`; the reviewed mobile error state
is `../review/cloud_mesh_dimensions_mobile.png`.

Before the first verified mesh, failures or Stop show the catalog image with
accurate viewer hints and retain invalid-field messages and the corresponding
mesh status. Original-preview retry remains available.

Generated previews require the exact `model/stl` media type and CAD files require
`application/zip`. Matching is case-insensitive and ignores semicolon-delimited
parameters, following [HTTP media-type rules](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3.1).
Mentioning the expected type only inside a parameter, or adding a subtype suffix,
does not pass validation. Invalid types release their unread bodies and return
retry controls immediately. Original catalog responses recognize HTML fallback
pages regardless of capitalization and retain the existing mesh hash check.

Once valid file headers arrive, preview and CAD requests switch from building
to receiving. A separate status shows the bytes actually received, using B, KiB
or MiB without trusting the stated response size or inventing a percentage.
Original catalog previews also show receipt progress without replacing saved
dimensions, validation errors or shared-link feedback. Completed transfers
switch to verification before their files become available. The cold-start
reminder ends when receipt starts. Progress clears on completion, failure, Stop,
timeout or model navigation; late bytes and old requests cannot hide a newer
transfer. The existing 15-minute waiting deadline includes transfer and
verification time.

`verify_transfer_progress_ui.py` has fifteen compiled-browser checks for actual
byte counts, misleading response sizes, zero-byte waits, delayed verification,
exact STL/CAD downloads and cached ZIP reuse, saved-file and rejected-file
feedback, late bytes, model switches, original retries, build reminders,
deadlines, failure details, edits during receipt, and mobile live status and
keyboard Stop. Real exported payloads use deliberately delayed readers and
hashes. Retry and build-reminder checks also delay the next response headers
and wait for that new stream, avoiding an obsolete reader's release handle.
Virtual clocks are installed before page scripts run. Its report and reviewed mobile image are
`../review/cloud_transfer_progress_validation.json` and
`../review/cloud_transfer_progress_mobile.png`.

During a preview or CAD build, Stop waiting restores editing and preserves the
last verified preview and current inputs. A 15-minute browser waiting deadline
provides the same recovery automatically, including startup and file transfer
time. The service may still finish its request and return busy while it does.
Late results cannot overwrite a newer preview, trigger a download, or unlock
a retry that is still building.

`verify_build_recovery.py` checks these cases with real exported CAD fixtures
and deliberately delayed headers or bodies. Its ten browser checks cover manual
stops, deadlines, retries, late results and service errors, navigation, invalid
drafts, missing previews, and a reachable keyboard-operated mobile stop button.
A virtual clock tests the waiting deadline without a real 15-minute wait.
Results are in `../review/cloud_build_recovery_validation.json`.

Verified STL and CAD downloads become available independently of the optional
3D viewer. While its module loads, the editor shows a labeled original catalog
image and the verified mesh dimensions. A late viewer arrival displays the
current verified mesh, including after a CAD download. Script or graphics
failures retain the files and image fallback; failed renderers release their
canvas and resources.

If graphics are interrupted after loading, the editor shows the original catalog
image while keeping verified mesh dimensions and files. When graphics return, it
redraws the current mesh with the same camera and edge display. Builds and CAD
downloads can continue during the interruption; invalid drafts, keyboard focus,
pending requests and cached CAD files are preserved. Recovery also follows model
navigation and does not open a closed editor or start another CAD build.

`verify_viewer_loading.py` has thirteen browser checks for delayed viewer loading,
original and customized STL/CAD downloads, late 3D upgrades, model switches,
closed editors, module failures, missing WebGL, rendering failures, and blocked
corrupt meshes, plus graphics loss and restoration during editing, builds,
navigation and mobile CAD downloads. The latter use the browser's real
[WebGL loss and restoration extension](https://developer.mozilla.org/en-US/docs/Web/API/WEBGL_lose_context)
with exported CAD fixtures and compiled viewer code. Its report is
`../review/cloud_viewer_loading_validation.json`; the before-fix evidence is
`../review/cloud_viewer_context_baseline.json`. Reviewed mobile images are
`../review/cloud_viewer_context_mobile.png` and
`../review/cloud_viewer_context_mobile_restored.png`.

`verify_transfer_ui.py` checks oversized original previews, custom previews and
CAD ZIPs, interrupted and empty transfers, cancellation during a pending read,
retries, and exact chunked STL/CAD downloads. Its thirty-five browser checks also
download the library's largest original STL and cover malformed service errors,
split UTF-8 messages, capped and interrupted error streams, cancellation,
five-second error recovery, useful delayed details, recovery before the first
preview, and exact retries. New checks reject invalid preview/CAD headers before
reading stalled bodies, cancel obsolete headers after Stop or navigation, leave
newer CAD retries waiting, recover before the first mesh, and preserve invalid
mobile drafts. Nonresponsive cancellation must not delay these recoveries.
Reused transport buffers must preserve exact original and customized STL files,
CAD ZIPs and split UTF-8 service errors; empty chunks must preserve the file
that follows. The stalled-error check holds virtual time still and verifies
recovery immediately before and after the five-second boundary.
It waits for the current request's reader and resumes the virtual clock in
cleanup even when an assertion fails, so later checks can complete.
Four further checks reject misleading STL/ZIP media types before reading stalled
bodies and retain exact verified files under mixed capitalization, whitespace and
media-type parameters. Each accepted CAD variant triggers a fresh export.
Real CAD fixtures and controlled
browser streams exercise the production frontend, including an incorrect
response size. Results are in `../review/cloud_transfer_validation.json`.

For environments without loopback networking, `verify_runtime.py --native` and
`verify_exports.py --native` run the actual isolated native job directly.
The browser verifiers accept `--offline` to serve the
compiled production assets through Playwright routes at a secure `.test` origin,
backed by those native CAD jobs or their exported fixtures for controlled failures.
These modes verify the runtime and browser behavior; they do not exercise the
Worker's HTTP routing or rate limiter. The native test helper keeps temporary CAD
exports in the workspace so Lib3MF can write under restricted Windows accounts.

`npm test` uses Node 24 or later and the prepared catalog/runtime bundle. Nine
request checks cover all 53 defaults, source-derived integer fields, continuous
dimensions, invalid objects and numeric values, unknown keys, byte limits,
stream cancellation, UTF-8 split across chunks, and export formats. Fourteen file
transfer checks cover exact byte order, the 8 MiB boundary, early cancellation,
interrupted and empty bodies, stopped reads and late bytes, and a cancellation
promise that never finishes, actual received-byte progress with misleading
response sizes, limit enforcement before progress, and stopped progress after
late bytes, reused buffers, tiny borrowed views with an odd byte limit, and
interleaved empty chunks. Twelve parameter and saved-dimension checks cover
all 53 defaults and field ranges, partial files, list order, counts, numeric
types and magnitude limits, units, UTF-8 byte limits and BOMs, and canonical kit
quantities and error-field identification. Re-run `prepare.py` after changing model defaults
or parameter types before checking or building the Worker.
Five clipboard checks cover ordering, superseded queued requests, synchronous
and asynchronous failures, and a stalled writer holding only the latest request.
Ten error-response checks cover readable service messages, malformed roots and
fields, the 16 KiB stream cap, interrupted and empty bodies, split UTF-8, stopped
reads and late bytes, a short error deadline, and prompt release even when a
reader ignores cancellation. Six mesh checks cover all catalog previews and
real custom/kit files, binary facet layout, finite values, positive extents,
dimension agreement, tessellation tolerance, and valid binary headers and
attribute bytes. All fifty-six unit tests pass.

## API

```http
POST /api/generate
Content-Type: application/json

{"model":"parts_tray","parameters":{"length":180,"height":30,"columns":4,"rows":3}}
```

Unspecified parameters use that model's defaults. A successful response contains
binary `model/stl`, a suggested filename, and `X-Model-Metadata` containing
URL-encoded JSON with the applied parameters, bounds, solid count, volume, units,
printability, and mesh SHA-256. Errors use JSON `{ "error": "…" }`: invalid input
400, unsupported geometry 422, rate limit 429, and busy/unavailable service 503.
`GET /api/health` reports the deployed runtime version and catalog count.

An optional `"format":"cad"` in the same request selects the CAD ZIP instead of
STL. `"format":"stl"` or omission retains the existing preview API. Other formats
are rejected before starting CAD work. ZIP responses use `application/zip` and
the same model metadata header, with `format` and `file_sha256` for verifying
the returned file. Assembly responses also include `kit` entries with component
names, quantities, and roles (`component` or `fit_coupon`). `mesh_sha256` still
identifies the live preview tessellation.
Downloads are limited to 8 MiB, with a 24 MiB uncompressed CAD-package limit
and the existing isolated 90-second job deadline.

The development follow-ups recorded in `../THREAD_SUMMARY.md`, including CAD
downloads, are local changes and have not been deployed to the public site.

The application and original models are covered by the parent Apache-2.0 license.
