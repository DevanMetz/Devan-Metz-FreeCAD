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
Original preview transfers recover after 15 seconds without headers or new file
bytes. Each positive receipt resets the inactivity timer so slower transfers can
finish. Empty chunks cannot keep a stalled request alive. Expired responses and
superseded requests cancel unused bodies or release their readers; late files
cannot replace a newer preview. Retry original preview reloads the static STL,
keeping field edits, file feedback, saved versions and history. CAD work keeps
its own deadline and Stop controls, and cached previews need no network timer.

`verify_original_idle_ui.py --offline` checks eleven browser recovery scenarios
with controlled time, including progressing and empty chunks, uncancellable
readers, late headers, raw drafts and local files, retries, CAD focus and exact
STL/ZIP downloads, cached history, assemblies, graphics fallback and mobile
keyboard use. Evidence and reviewed layouts are under
`../review/cloud_original_idle_*`. Nine unit checks cover the inactivity
boundary, timer cleanup, parent cancellation, header races and transfer limits.

The preview panel's Check printer fit uses dimensions measured from the verified
STL, comparing them with a visitor's usable build volume in millimeters. It
allows a 90° turn on the bed while keeping the saved Z orientation. Results
describe the last verified preview and identify unbuilt or invalid edits.
Reference assemblies direct visitors to check each printable component.
Printer dimensions persist in this browser when storage is available; Clear
build volume removes them. These settings do not edit model parameters or
trigger CAD requests. Brims and printer clearances remain slicer considerations.

Incomplete or invalid printer entries keep the last complete saved build volume,
including in other tabs and after refresh. Complete three positive measurements
to save changes. Clear build volume or empty all three fields to remove them;
a partly typed number such as 1e still counts as an invalid entry.

Saved printer settings also update other open tabs. Idle fields follow the latest
valid settings or clearing; focused, incomplete or unsaved entries stay in place.
Use saved build volume also appears for local incomplete edits or failed saves
when a saved profile is known. It reads the latest settings afresh, focuses
Width, and keeps the model, verified files and saved versions.
Malformed, oversized or unavailable storage keeps the current check available
with retry guidance. External updates never write back or change model fields,
version Undo, build progress, preview files or cached CAD downloads.

`verify_printer_sync_ui.py --offline` exercises twenty real two-tab scenarios,
including queued events, corrupt and denied reads, failed writes, active builds,
late previews, saved versions, early catalog loading, history and refresh,
assembly components and mobile keyboard use. Evidence and reviewed layouts are
under `../review/cloud_printer_sync_*`. Four additional checks cover incomplete
and native invalid entries, valid saves and clearing, refresh, deferred external
settings, pending builds and exact cached CAD files. The before-fix probe and
reviewed layouts are under `../review/cloud_printer_edit_*`. Four local recovery
checks cover failed saves and clearing, fresh and unreadable settings, an absent
saved profile, invalid model drafts, version Undo, cached CAD reuse, pending
builds and mobile focus. Their baseline and reviewed layouts are under
`../review/cloud_printer_restore_*`.

`verify_printer_fit_ui.py --offline` checks original and custom meshes, exact
boundaries, bed rotation and height, measured STL extents versus CAD rounding,
dirty fields, failed previews, missing graphics, cached CAD files, component
navigation, history and refresh, malformed or denied storage, pending builds,
and keyboard/mobile controls. Results and reviewed layouts are saved under
`../review/cloud_printer_fit_*`.

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

The Saved dimensions section also holds up to 20 named versions in this browser.
Names are scoped to a model; opening a version restores its validated scalar or
ordered list values and navigates to that model. Valid unbuilt measurements can
be saved, but changed versions still need Update preview before downloading.
Matching versions reuse the current verified mesh and cached CAD/kit files.
Assembly quantities come from the catalog, and stored geometry details cannot
replace verified previews. Removing a version keeps the editor's fields and
files. Save dimensions provides a portable file outside browser storage.

Version actions read current storage, preserve existing records on failed writes,
reject duplicate names for the same model, and enforce a 64 KiB UTF-8 record
limit. Malformed or incompatible records are preserved with recovery guidance;
denied storage and quota failures keep ordinary editing and downloads usable.
Save and Open version supersede older file reads; active CAD work disables
version actions without interrupting the build. Twelve browser checks cover
persistence, fine decimals, lists, assemblies, history, exact STL/CAD reuse,
validation, limits, storage failures, late previews/imports and mobile keyboard
controls. Evidence and reviewed layouts are under `../review/cloud_versions_*`.

Rename version changes the selected entry’s name using the name field above.
Replace dimensions stores the current validated measurements in the selected
entry, retaining its name, identity and position. It is enabled only for a
version of the open model. Replacements work with twenty saved entries, while
unchanged actions avoid writes and remain usable when storage is full. Names
still reject same-model conflicts, including changes saved by another view.
Failed reads, writes, missing entries and invalid fields keep existing data.

These actions keep current fields, preview files, CAD caches and history.
Changed measurements still require Update preview. Both supersede older backup
imports; replacement also supersedes a pending dimensions-file read. Renaming
keeps that independent file read and its feedback. An opened version’s new name
survives a late original preview. Active CAD work disables both controls.
Fourteen compiled-browser checks cover precise decimals/lists, full libraries,
canonical assemblies, exact downloads, cached CAD reuse, storage failures,
late reads, Stop recovery and mobile keyboard use. Evidence and reviewed layouts
are under `../review/cloud_version_edits_*`.

Undo last version change restores the library before its latest successful Save,
Rename, Replace dimensions, Remove or Import action, including a multi-entry
backup import. Identities, order, names, exact measurements and canonical assembly
quantities are restored together. The previous selection returns when it still
exists, and keyboard focus returns to the version list. Current editor fields,
typed names, field errors, history, preview files and cached CAD remain intact.

Undo keeps one in-memory snapshot in this tab. Another successful change replaces
it; unchanged renames/replacements, repeated imports and failed actions
leave the last meaningful change available. Reloading clears it. External library
changes discard it, while unrelated or unchanged storage events keep it. The
restore operation also compares freshly validated storage with the captured
result, so a newer change is kept even before its storage event arrives.
Malformed records and failed reads/writes preserve data; failed Undo writes can
be retried. The snapshot captures the same storage read used by the mutation,
preventing a second read from separating its input from the recorded history.
A baseline reproduced an intervening version lost by the earlier double read.
Undo supersedes pending backup reads, keeps independent dimensions-file
feedback, and is disabled during CAD work. Thirteen compiled-browser checks cover
full libraries, all mutations, exact downloads and cached CAD, assemblies,
newer entries, failed writes/retries, pending files and mobile keyboard use.
Evidence and reviewed layouts are under `../review/cloud_versions_undo_*`.

Saved-version lists also refresh after changes in another tab, including Save,
Rename, Replace dimensions, Remove and clearing browser storage. The selected
identity stays selected while it exists. Removing it clears the selection and
disables stale actions; if a focused action becomes unavailable, keyboard focus
returns to the list. Editor fields, an unfinished name, history, preview files,
cached CAD, field errors, dimensions-file feedback and CAD progress remain intact.
Opening a changed entry still requires an explicit Open version action.

Synchronization reads the latest storage and validates it against the current
catalog instead of trusting event payloads. Unrelated keys, session storage and
unchanged canonical records are ignored. Invalid or denied reads leave storage
untouched, disable stale library actions and show a separate recovery notice.
Valid later changes restore the list, including an empty library. Pending backup
imports continue and merge against fresh records; capacity failures stay atomic.
Original previews use a renamed opened entry’s current name. Changes before
catalog readiness are picked up by its initial read; closed editors stay current
without moving library focus. Local actions dismiss the synchronization notice.
Twelve checks use two real tabs, with exact STL/CAD fixtures, malformed data,
storage denial, queued events, pending files/builds and mobile keyboard review.
Evidence is under `../review/cloud_versions_sync_*`.

Export versions downloads `everyday-prints-versions.json`, containing all names
and canonical dimensions with format `everyday-prints-versions` and version 1.
Import versions validates the whole backup before merging it into current browser
storage. Entries get fresh local identities; existing entries retain theirs.
Conflicting names within a model receive a numeric suffix, and repeated imports
skip identical entries, including previously numbered conflicts. A failed read,
invalid record, storage error or 20-version capacity failure keeps existing data.
All backup transfers are bounded to 64 KiB of UTF-8, with BOM files supported.

Imports save versions for later opening and preserve editor fields, verified
previews, CAD caches and model-file feedback. Stalled local reads recover after
15 seconds. A newer named action or file selection supersedes older reads;
model navigation, closing the editor and CAD work also discard late imports.
Backup controls are disabled during CAD work. Fourteen browser checks cover
portable exports, a second browser, exact list/STL and cached CAD correspondence,
conflict/repeat handling, atomic rejection, limits, stalled reads, overlapping
actions, storage failures and desktop/mobile keyboard use. Evidence and reviewed
layouts are under `../review/cloud_version_backups_*`.

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

The lockfile overrides Sharp to `^0.35.5` to patch the SVG decoder described in
[the maintainer advisory](https://github.com/advisories/GHSA-wq5f-xc86-pv6w).
Both Miniflare dependency paths receive the patch while the Cloudflare, Vite
and TypeScript versions stay unchanged. The clean install reports zero npm audit
findings, including development dependencies.

For this checkpoint, `python verify_dependencies.py` verifies the full audit,
the installed native decoder, SVG conversion into four image formats and all
53 catalog PNGs. Reports are under `../review/cloud_dependency_*`; the build
report records unchanged application hashes and the rechecked browser flows.

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
python verify_field_revert_ui.py
python verify_dimensions_ui.py
python verify_zip_dimensions_ui.py
python verify_dimension_drop_ui.py
python verify_import_actions_ui.py
python verify_printer_fit_ui.py
python verify_printer_sync_ui.py
python verify_versions_ui.py
python verify_version_backups_ui.py
python verify_version_edits_ui.py
python verify_versions_sync_ui.py
python verify_versions_undo_ui.py
python verify_dimensions_preview_ui.py
python verify_original_retry_ui.py
python verify_original_idle_ui.py
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
in the current tab, with a shared 32 MiB file budget and up to 64 saved views. Reloading
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

Measurement inputs have a minimum height of 44 px, matching the main actions.

`verify_build_focus_ui.py` records fourteen keyboard checks for completion and
exact files, Stop, field submission, cached CAD reuse, the two-request original
CAD path, service failures, deadlines, preserved field focus and mobile
navigation. Delayed 3D loading also checks visible Stop and download controls
at four phone/desktop sizes, exact cached ZIPs and dimension-bearing STL/CAD
filenames. Choosing a measurement during the request preserves its focus and
visible bounds through viewer loading and CAD completion. The report includes
measured rectangles before/after loading and download.
Results are in `../review/cloud_build_focus_validation.json`; reviewed layouts
are `../review/cloud_build_focus_mobile.png` and
`../review/cloud_build_focus_delayed_desktop.png`, with the short phone view in
`../review/cloud_build_focus_delayed_mobile.png`.

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

Each changed measurement also shows its exact last verified preview value and a
Revert value action. Restoring it changes only that input and returns focus to
it, keeping other raw drafts, including invalid values, and saved-version names.
Numeric formatting alone does not count as a change; list order does. The preview
note includes the field's units and its accessible description. Invalid drafts
can return to the verified value. No action appears until a preview is verified,
and individual actions stay disabled while CAD work is active.

The baseline follows the latest verified preview, including after successful
custom builds, failed requests, Stop and original-preview recovery. Restoring
one input discards older dimensions-file reads while independent library backups
can complete. History and same-tab draft recovery retain the remaining edits.
STL and cached CAD/kit downloads are reused only when the entire form matches the
verified preview. Revert edits continues to restore all measurements together.

`verify_field_revert_ui.py` has thirteen compiled-browser checks covering all 53
model schemas, scalar/list/count formatting, invalid drafts, exact custom STL and
cached CAD reuse, new and failed previews, delayed files, library Undo, history,
assemblies, unavailable graphics and mobile keyboard controls. The baseline
records the earlier all-fields-only recovery. Results and reviewed layouts are
under `../review/cloud_field_revert_*`.

Open Saved dimensions above the parameter form to save or load measurements.
Save dimensions downloads `<model>-dimensions.json` with the current inputs,
millimeter units and canonical assembly kit quantities. It works before building
a preview. Load dimensions accepts a downloaded CAD or kit ZIP directly,
its extracted `parameters.json`, or a saved dimensions JSON file. It
opens its model and fills the fields without starting CAD work. Partial parameter
objects use the model's defaults for omitted fields. Update preview is required
for changed dimensions; matching inputs retain the verified STL and cached ZIP.

You can also drop one saved dimensions JSON file or CAD/kit ZIP into the file
box in Saved dimensions. The box highlights for file drags; dropping uses the
same bounded importer as Load dimensions. Multiple or rejected files keep the
current measurements and verified downloads. Pending builds stay in progress.
Load dimensions remains available for keyboard and touch use.

`verify_dimension_drop_ui.py --offline` has nine checks. Its desktop case sends
an exported ZIP from disk through Chromium's trusted native drag pipeline.
It covers exact dropped-file downloads,
JSON model switches and history, kit inventories, rejected and oversized files,
busy CAD, late reads, drag feedback and the phone chooser with unavailable 3D.
Evidence and reviewed layouts are under `../review/cloud_dimension_drop_*`.

JSON files are limited to 16 KiB. Model and parameter names, units, numeric types,
counts, list lengths and numeric bounds are validated before the form changes.
Direct ZIP imports read only the top-level `parameters.json` record. Archives
are limited to 8 MiB, 128 entries and 24 MiB of declared uncompressed contents;
the dimensions record stays within the existing 16 KiB limit, including actual
decompressed bytes. Stored and deflated records have their CRC and UTF-8 checked.
Duplicate, missing or nested records and unsupported/encrypted ZIPs are rejected
without changing the current model, fields or retained STL/CAD files. Imported
geometry metadata and kit inventories never replace the verified preview or
canonical catalog data. Update preview still verifies a mesh before downloading
customized files. The optional [zip.js reader](https://gildas-lormeau.github.io/zip.js/)
loads only for ZIP selection and uses browser decompression; JSON imports stay
available when ZIP reading is unavailable. Its BSD notice is in
`THIRD_PARTY_NOTICES.md`.

`verify_zip_dimensions_ui.py --offline` records twelve checks for real CAD and
all six kit ZIPs, exact decimal/list parameters, chooser labels, cached STL/CAD
bytes and names, history, malformed archives, caps, late reads, deadlines,
newer actions, busy downloads, unavailable graphics and ZIP reading, and phone
keyboard focus. These run under the production content security policy.
Evidence and reviewed layouts are under `../review/cloud_zip_dimensions_*`.

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

When recovery hides the focused Retry original preview button, the first
measurement receives focus near the center of the visible editor. It stays
visible when the optional 3D toolbar appears and in short phone or desktop
windows. Moving to another control during the request keeps that control’s
focus, and closing or changing models discards late restoration.

`verify_original_retry_ui.py` has twenty-three browser checks for missing, HTML,
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

Update preview reuses a retained verified native preview from another remembered
view when its model and canonical parameters match, including previews without
a CAD ZIP. The stored mesh passes normal hash, metadata and geometry verification;
a retained matching ZIP is then attached if available. This avoids duplicate builds
after reopening a library card or reapplying a named version or dimensions file.
ZIP reuse with an already verified preview requires both an archive and the exact
mesh hash. Without a retained ZIP, the first CAD download builds and verifies one
against the current preview. Catalog meshes still receive the usual native refresh.
Changed parameters use the normal service build when no matching preview exists.

A CAD response reporting a different valid mesh hash marks that preview for a
fresh service build. Update preview skips affected mesh-only cache records,
including views sharing the same metadata, while retaining the verified STL.
Complete verified ZIPs remain reusable. Stop, timeouts and failed refreshes keep
the old STL and the need for a fresh build; late CAD replies from superseded
views cannot mark a newer preview. Successful native replies can be reused again.

`verify_cad_cache_recovery_ui.py --offline` has five checks for mismatch recovery,
exact new STL/CAD files and dimension-bearing filenames, history aliases, imported
dimensions, Revert, stopped and expired replies, service and mesh verification
failures, delayed CAD headers, unrelated complete downloads and mobile keyboard
use. Its alternative native STL encoding changes only the 80-byte header and
retains every facet; the ZIP contains that exact STL and updated metadata. The
baseline restored the rejected cached mesh and failed CAD twice without a fresh
preview request. Evidence and reviewed desktop/phone layouts are under
`../review/cloud_cad_cache_recovery_*`.

Four preview-only browser checks cover STL-only named versions, exact files and
dimension-bearing names, native default previews, reference assemblies, first CAD
and kit exports, failed CAD requests, dimensions files, invalid drafts, changed
parameters, Stop with delayed verification and mobile keyboard focus. The baseline
repeated the same native preview request after reopening an STL-only named version.
Evidence and reviewed desktop/phone layouts are under `../review/cloud_preview_reuse_*`.

Local restoration uses the existing Stop and 15-minute deadline controls, preserves
newer edits and focus, and ignores completion after Stop or model navigation.
Its status describes restoration, and Stop feedback does not claim a service
request is still running. The reopen baseline made two unnecessary requests for
an identical original CAD ZIP; evidence and reviewed layouts are under
`../review/cloud_download_reuse_*`. A separate four-size saved-file focus probe
confirmed existing measurement visibility in `../review/cloud_saved_focus_probe.json`.

Browser Back and Forward restore retained verified CAD and parts-kit ZIPs
alongside their matching preview meshes. Repeat downloads keep the exact bytes
and filenames and avoid another CAD request. Invalid or unbuilt fields still
require correction or Revert edits before downloading. Updating the preview
associates downloads with its new mesh, and late verification cannot attach an
older ZIP to a newer model view.

The history file cache holds at most 32 MiB across up to 64 remembered views.
Verified preview meshes take priority, then newer CAD/kit ZIPs fill the remaining
budget. Reused ArrayBuffers and CAD Blobs count once by reference identity,
so several history entries sharing the same files cannot consume the budget
repeatedly. Separately allocated files still count individually. Evicting an
older ZIP keeps its retained preview available; downloading that ZIP again uses
the normal verified CAD request.

`verify_history_downloads_ui.py --offline` has sixteen browser checks for customized
and original downloads, one-time original CAD refreshes, repeated history,
invalid and dirty drafts, Revert edits and replacement previews, reference kits
and component navigation, delayed verification superseded by another view,
mobile keyboard focus and exact filenames. Six distinct native CAD ZIPs padded to about 6 MiB
each exercise real budget eviction while preserving their original CAD members.
Two more checks repeatedly reopen shared native files, observe object identity
without retaining them, and verify both older and newer exact downloads with
only four native requests after six or twenty reopened views. A native 36-pocket
tray supplies a mesh whose twenty references exceed 32 MiB. The earlier duplicate
accounting caused five and eighteen requests. Evidence and reviewed desktop and
phone layouts are under `../review/cloud_shared_history_*`.
The report, duplicate-request baseline and reviewed desktop/phone layouts are
under `../review/cloud_history_downloads_*`.

Verified STL and CAD downloads become available independently of the optional
3D viewer. While its module loads, the editor shows a labeled original catalog
image and the verified mesh dimensions. A late viewer arrival displays the
current verified mesh, including after a CAD download. Script or graphics
failures retain the files and image fallback; failed renderers release their
canvas and resources.

Replacing a mesh in the same open model preserves the chosen camera angle,
zoom, pan and Edges setting, including the original-mesh refresh for CAD downloads.
Camera and pan offsets and clipping distances scale with the new mesh radius
around its updated center. Choices made while a build is pending take effect
when its mesh arrives. Closing the editor or opening another model resets the
view to 3D with Edges off.

The verified 3D canvas is a Tab stop with a visible focus outline. Arrow keys
pan, Shift + arrows orbit, + / − (or =) zoom, and Home frames the model in 3D.
Tab continues to the view buttons and Escape closes the editor. Keyboard zoom
stays within the camera's clipping range, and Home keeps the Edges choice.
Browser shortcuts retain their default action, while arrow keys in measurements
continue to edit those fields. An unavailable canvas leaves the Tab order. If it
has focus when graphics are lost, the first measurement receives visible focus;
graphics recovery keeps that field's focus and the current camera pose.

The canvas has a labelled `application` role and described keyboard instructions,
following the [WAI-ARIA application role](https://www.w3.org/TR/wai-aria-1.2/#application).

If graphics are interrupted after loading, the editor shows the original catalog
image while keeping verified mesh dimensions and files. When graphics return, it
redraws the current mesh with the same camera and edge display. Builds and CAD
downloads can continue during the interruption; invalid drafts, keyboard focus,
pending requests and cached CAD files are preserved. Recovery also follows model
navigation and does not open a closed editor or start another CAD build.

`verify_viewer_loading.py` has twenty-three browser checks for delayed viewer loading,
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

Four additional viewer checks use real pointer orbit, wheel zoom and right-drag
pan, named views, keyboard controls on a phone, a native-generated taller tray,
larger and smaller meshes, pending view choices, CAD refreshes and cached exact
files. Graphics recovery also checks framing after a changed mesh arrives.
The camera reset baseline and reviewed desktop and phone layouts are under
`../review/cloud_camera_update_*`.

Six keyboard checks measure camera movement and zoom limits from real key events,
preserve framing through pending preview/CAD requests, verify exact cached files
and names, and cover late loading, invalid drafts, Tab/Escape navigation, graphics
loss and mobile focus bounds. Accessibility-enabled Chromium checks the canvas
role and hidden-focus warnings. The baseline records the skipped canvas and
unchanged camera after each proposed key. Evidence and reviewed layouts are
`../review/cloud_keyboard_viewer_baseline.json`,
`../review/cloud_viewer_loading_validation.json` and
`../review/cloud_keyboard_viewer_desktop.png` / `../review/cloud_keyboard_viewer_mobile.png`.

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
attribute bytes. Seven named-version checks cover all 53 defaults, exact exported
decimals and lists, canonical assembly inventory, duplicate names, storage caps,
corrupt records, failed writes and changes saved by another view. Six more checks
cover portable backups for all 53 models, conflict numbering and repeated imports,
Unicode names, exact decimals/lists, canonical inventory, atomic rejection,
UTF-8/BOM boundaries, capacity and failed writes. Five additional checks cover
in-place renaming for every model, decimal/list replacement in full libraries,
fresh records, invalid fields, model mismatches, corrupt data and unchanged
actions during quota failures. Five Undo checks cover restoration for all 53
models, exact values/order through every mutation, guards against newer entries,
invalid snapshots, corrupt storage, failed writes/retries and canonical inventory.
Nine ZIP dimensions checks cover all real exported CAD/kit fixtures, stored
and deflated records, UTF-8/BOM boundaries, ZIP/JSON caps, missing/nested/duplicate
and contradictory records, CRC corruption, archive/record expansion, falsely
small size fields, encryption/compression recovery, cancellation and unavailable decompression with JSON recovery.
All 102 unit tests pass.

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
