import MiniSearch from 'minisearch';
import { MAX_FILE_BYTES, readFile } from './transfer.js';
import { responseProblem } from './problems.js';
import { MAX_DIMENSIONS_BYTES, dimensionParameters, dimensionRecord, parameterError, savedDimensions } from './dimensions.js';
import { clipboardQueue } from './clipboard.js';
import { loadDraft, saveDraft } from './drafts.js';
import { verifyMesh } from './mesh.js';
import { readOriginal } from './original.js';
import { PRINTER_STORAGE, readPrinterVolume, validPrinterVolume } from './printer.js';
import { MAX_VERSIONS_BYTES, VERSIONS_KEY, importVersionBackup, readVersions, removeVersion, renameVersion, replaceVersion, saveVersion, undoVersionChange, versionBackup, versionName } from './versions.js';

const $ = id => document.getElementById(id);
const escape = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const sizeText = values => values.map(value => Number(value.toFixed(2))).join(' × ');
const dialog = $('editor');
const state = { models: [], kind: '', item: null, parameters: null, previewParameters: null, blob: null, buffer: null, meshSize: null, metadata: null, cad: null, busy: false, catalogLoading: false, epoch: 0 };
let searchIndex, viewer, viewerPromise, abort;
let activeEntry;
let dimensionsRead = 0;
let dimensionsLoading;
let appliedDimensions = null;
let originalFeedback;
let shareRequest = 0;
let buildFocus;
let versions = [];
let versionsRead = 0;
let versionsLoading = false;
let versionUndo = null;
const copyLink = clipboardQueue(text => navigator.clipboard.writeText(text));
const savedPages = new Map();
const cadMismatches = new WeakSet();
const HISTORY_CACHE_BYTES = 32 * 1024 * 1024;
const BUILD_WAIT_MS = 15 * 60 * 1000;
const MAX_CATALOG_BYTES = 2 * 1024 * 1024;
const printerInputs = ['printer-width', 'printer-depth', 'printer-height'].map($);
let printerStored = null;

function printerVolume() {
  const volume = printerInputs.map(input => input.valueAsNumber);
  return validPrinterVolume(volume) ? volume : null;
}

function updatePrinterFit() {
  const result = $('printer-fit-result');
  result.dataset.fit = '';
  $('printer-mesh-size').hidden = !state.meshSize || state.item?.kind !== 'print';
  $('printer-preview-note').hidden = true;
  const volume = printerVolume();
  const started = printerInputs.some(input => input.value || input.validity.badInput);
  for (const input of printerInputs) input.setAttribute('aria-invalid', String(started && (!Number.isFinite(input.valueAsNumber) || input.valueAsNumber <= 0)));
  if (state.item?.kind === 'assembly') {
    result.textContent = 'Reference assembly. Open the printable parts below to check each part.';
    return;
  }
  if (state.meshSize) {
    $('printer-mesh-size').textContent = `Verified STL: ${sizeText(state.meshSize)} mm (X × Y × Z).`;
    let current = false;
    try { current = sameParameters(readParameters(), state.previewParameters); } catch { /* The check still describes the verified mesh. */ }
    $('printer-preview-note').hidden = current;
  }
  if (!volume) {
    result.textContent = 'Enter a positive width, depth and height in millimeters.';
    return;
  }
  if (!state.meshSize) {
    result.textContent = 'Waiting for a verified STL to check its size.';
    return;
  }
  const [x, y, z] = state.meshSize;
  const [width, depth, height] = volume;
  if (x <= width && y <= depth && z <= height) {
    result.dataset.fit = 'fits';
    result.textContent = 'Fits this build volume in the saved print orientation.';
  } else if (y <= width && x <= depth && z <= height) {
    result.dataset.fit = 'rotate';
    result.textContent = 'Fits after a 90° turn on the bed in your slicer.';
  } else {
    result.dataset.fit = 'large';
    result.textContent = 'Too large for this build volume, including a 90° turn on the bed.';
  }
}

function printerSyncMessage(text = '', error = false, apply = false) {
  const note = $('printer-sync-message');
  note.textContent = text;
  note.hidden = !text;
  note.classList.toggle('error', error);
  $('apply-printer-volume').hidden = !apply;
}

function samePrinterForm(volume) {
  return volume ? JSON.stringify(printerVolume()) === JSON.stringify(volume)
    : printerInputs.every(input => input.value === '' && !input.validity.badInput);
}

function applyPrinterVolume(volume) {
  printerStored = volume;
  printerInputs.forEach((input, axis) => { input.value = volume?.[axis] ?? ''; });
  $('printer-profile-note').textContent = volume ? 'Build volume saved in this browser.' : 'Use your printer’s usable build volume.';
  updatePrinterFit();
}

function savePrinterVolume() {
  const volume = printerVolume();
  if (!volume && !samePrinterForm(null)) {
    $('printer-profile-note').textContent = 'Complete a positive width, depth and height to save changes.';
    if (printerStored && $('apply-printer-volume').hidden)
      printerSyncMessage('Your saved build volume is kept. Use saved build volume to restore it.', false, true);
    updatePrinterFit();
    return;
  }
  try {
    if (volume) localStorage.setItem(PRINTER_STORAGE, JSON.stringify(volume));
    else localStorage.removeItem(PRINTER_STORAGE);
    printerStored = volume;
    printerSyncMessage();
    $('printer-profile-note').textContent = volume ? 'Build volume saved in this browser.' : 'Use your printer’s usable build volume.';
  } catch {
    $('printer-profile-note').textContent = 'Build volume stays here while this page is open.';
    if (printerStored && !samePrinterForm(printerStored) && $('apply-printer-volume').hidden)
      printerSyncMessage('Changes could not be saved. Use saved build volume to restore your printer settings.', true, true);
  }
  updatePrinterFit();
}

function restorePrinterVolume() {
  try { applyPrinterVolume(readPrinterVolume(localStorage)); }
  catch { /* Printer checks remain available when saved settings cannot be read. */ }
  updatePrinterFit();
}

function syncPrinterVolume(event) {
  if (event.key !== PRINTER_STORAGE && event.key !== null) return;
  try {
    if (event.storageArea !== localStorage) return;
    const volume = readPrinterVolume(localStorage);
    const recovering = $('printer-sync-message').classList.contains('error');
    if (JSON.stringify(volume) === JSON.stringify(printerStored) && !recovering) return;
    const editing = printerInputs.includes(document.activeElement) || !samePrinterForm(printerStored);
    if (editing) {
      printerStored = volume;
      $('printer-profile-note').textContent = 'Current entries are kept in this tab.';
      printerSyncMessage('Saved build volume changed in another tab. Current entries are kept. Use saved build volume to apply the latest settings.', false, true);
    } else {
      applyPrinterVolume(volume);
      printerSyncMessage(recovering ? 'Saved printer settings are available again.' : 'Build volume updated from another tab. Model measurements and files are kept.');
    }
  } catch (error) {
    printerSyncMessage(error.name === 'SecurityError' ? 'Saved printer settings are unavailable in this browser. Current build volume is kept. Try Use saved build volume again.' : error.message, true, true);
  }
}

function historyEntry() {
  const model = new URL(location.href).searchParams.get('model');
  const saved = history.state?.everydayPrints;
  const entry = saved && typeof saved.id === 'string' && (saved.depth === null || (Number.isInteger(saved.depth) && saved.depth >= 0))
    ? { ...saved, model } : { id: crypto.randomUUID(), depth: model ? null : 0, model };
  history.replaceState({ ...history.state, everydayPrints: entry }, '', location.href);
  return entry;
}

function navigationURL(url, push = false) {
  const model = url.searchParams.get('model');
  const entry = push ? { id: crypto.randomUUID(), model, depth: model ? (activeEntry.depth === null ? null : activeEntry.depth + 1) : 0 } : { ...activeEntry, model };
  history[push ? 'pushState' : 'replaceState']({ ...history.state, everydayPrints: entry }, '', url);
  activeEntry = entry;
}

function rememberPage(updateURL = false) {
  if (!activeEntry) return;
  let saved;
  if (dialog.open && state.item) {
    saved = { model: state.item.name, values: formValues(),
      buffer: state.buffer, metadata: state.metadata, previewParameters: state.previewParameters, cad: state.cad };
    if (updateURL) {
      try {
        const parameters = readParameters();
        const url = new URL(location.href);
        if (sameParameters(parameters, state.item.defaults)) url.searchParams.delete('p');
        else url.searchParams.set('p', JSON.stringify(parameters));
        navigationURL(url);
      } catch { /* Invalid drafts stay in this tab, and cannot become share links. */ }
    }
  } else if (!activeEntry.model) {
    saved = { search: $('search').value, category: $('category').value, kind: state.kind,
      scrollY: window.scrollY, focusModel: document.activeElement.closest('[data-model]')?.dataset.model };
  } else return; // A close followed by popstate must not overwrite the saved editor.
  savedPages.delete(activeEntry.id);
  savedPages.set(activeEntry.id, saved);
  while (savedPages.size > 64) savedPages.delete(savedPages.keys().next().value);
  let bytes = 0;
  const buffers = new Set();
  for (const page of [...savedPages.values()].reverse()) {
    if (!page.buffer || buffers.has(page.buffer)) continue;
    if (bytes + page.buffer.byteLength > HISTORY_CACHE_BYTES) page.buffer = page.metadata = page.previewParameters = null;
    else {
      buffers.add(page.buffer);
      bytes += page.buffer.byteLength;
    }
  }
  const blobs = new Set();
  for (const page of [...savedPages.values()].reverse()) {
    if (!page.buffer) page.cad = null;
    else if (page.cad && !blobs.has(page.cad.blob)) {
      if (bytes + page.cad.blob.size > HISTORY_CACHE_BYTES) page.cad = null;
      else {
        blobs.add(page.cad.blob);
        bytes += page.cad.blob.size;
      }
    }
  }
}

function restoreLibrary(saved, focus = true) {
  if (saved && !saved.model) {
    $('search').value = saved.search;
    $('category').value = saved.category;
    state.kind = saved.kind;
    document.querySelectorAll('[data-kind]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.kind === state.kind)));
    filter();
    window.scrollTo(0, saved.scrollY);
  }
  if (focus) {
    const card = saved?.focusModel && document.querySelector(`[data-model="${saved.focusModel}"]`);
    (card || $('library-title')).focus({ preventScroll: true });
  }
}

async function restoreLocation() {
  if (!searchIndex) return;
  const restoring = Boolean(activeEntry);
  const entry = historyEntry();
  // Keep the requested record available while saving/pruning the departing view.
  const item = state.models.find(model => model.name === entry.model);
  const record = savedPages.get(entry.id) || (item && loadDraft(entry.id, item));
  const saved = record && { ...record };
  rememberPage();
  activeEntry = entry;
  history.scrollRestoration = 'manual';
  const params = new URL(location.href).searchParams;
  const model = params.get('model');
  $('link-notice').hidden = !params.has('model') || !!item;
  if (params.has('model') && !item) {
    const url = new URL(location.href);
    url.searchParams.delete('model'); url.searchParams.delete('p');
    activeEntry.depth = 0;
    navigationURL(url);
  }
  let supplied, parameterError;
  try {
    if (item && params.has('p')) {
      if (params.get('p').length > 10000) throw new Error('The shared dimensions are too large.');
      supplied = JSON.parse(params.get('p'));
    }
  } catch (error) { parameterError = error instanceof SyntaxError ? 'The shared dimensions are not valid JSON.' : error.message; }
  if (item) await openModel(model, supplied, { navigation: false, saved, parameterError });
  else {
    if (dialog.open) dialog.close();
    restoreLibrary(saved, restoring);
  }
}

function closeEditor() {
  if (!dialog.open) return;
  rememberPage(true);
  dialog.close();
  if (activeEntry.depth !== null && activeEntry.depth > 0) history.go(-activeEntry.depth);
  else {
    // A directly opened share link has no library entry to return to.
    const url = new URL(location.href);
    url.searchParams.delete('model'); url.searchParams.delete('p');
    navigationURL(url, true);
    rememberPage();
    restoreLibrary(savedPages.get(activeEntry.id));
  }
}

function filter() {
  const query = $('search').value.trim();
  const category = $('category').value;
  $('reset-search').hidden = !query && !category && !state.kind;
  // Visitors can enter filters while the catalog is loading or awaiting a retry.
  if (!searchIndex) return;
  const found = query ? searchIndex.search(query, { prefix: true, fuzzy: .2, combineWith: 'AND', boost: { title: 3, tags: 2 } }).map(match => state.models.find(model => model.name === match.id)) : state.models;
  const models = found.filter(model => (!state.kind || model.kind === state.kind) && (!category || model.category === category));
  $('result-count').textContent = `${models.length} ${models.length === 1 ? 'model' : 'models'}`;
  $('catalog').innerHTML = models.map(model => `<button class="card" data-model="${escape(model.name)}" aria-label="Customize ${escape(model.title)}"><div class="card-image"><img src="${escape(model.image)}" alt="${escape(model.title)}" width="1000" height="750" loading="lazy"><span class="card-number">${String(model.number).padStart(2, '0')}</span><span class="card-open" aria-hidden="true">↗</span></div><div class="card-content"><span class="card-category">${escape(model.category)}</span><h3>${escape(model.title)}</h3><p class="card-size">${sizeText(model.bounds_mm)} mm</p><div class="card-bottom"><span class="kind-badge ${model.kind === 'assembly' ? 'reference' : ''}">${model.kind === 'assembly' ? 'Assembly · view only' : 'Printable part'}</span><span class="card-action">${model.kind === 'assembly' ? 'Explore' : 'Customize'} ↗</span></div></div></button>`).join('');
  $('empty').hidden = models.length > 0;
}

function resetFilters() {
  $('search').value = '';
  $('category').value = '';
  state.kind = '';
  document.querySelectorAll('[data-kind]').forEach(button => button.setAttribute('aria-pressed', String(!button.dataset.kind)));
  filter();
}

function message(text, error = false) {
  $('form-message').textContent = text;
  $('form-message').classList.toggle('error', error);
}

function clearTransfer() {
  $('transfer-status').hidden = true;
  $('transfer-status').textContent = '';
}

function transferProgress(label, epoch) {
  const show = text => {
    if (epoch !== state.epoch || !dialog.open) return;
    const status = $('transfer-status');
    status.hidden = false;
    if (status.textContent !== text) status.textContent = text;
  };
  const receive = bytes => {
    const size = bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
    show(`Receiving ${label}… ${size} received`);
  };
  receive(0);
  return { receive, verify: () => show(`Verifying ${label}…`),
    finish: () => { if (epoch === state.epoch) clearTransfer(); } };
}

function clearDimensionsError() {
  $('dimensions-error').textContent = '';
  $('dimensions-error').hidden = true;
}

function clearFieldErrors() {
  for (const input of $('parameter-fields').querySelectorAll('input')) {
    input.removeAttribute('aria-invalid');
    input.setCustomValidity('');
    const note = $(`error-${input.dataset.parameter}`);
    note.textContent = '';
    note.hidden = true;
  }
}

function invalidParameters(error, focus = false, report = true) {
  const input = error.parameter && $(`param-${error.parameter}`);
  if (input) {
    input.setAttribute('aria-invalid', 'true');
    input.setCustomValidity(error.message);
    const note = $(`error-${error.parameter}`);
    note.textContent = error.message;
    note.hidden = false;
    if (focus) {
      input.focus({ preventScroll: true });
      input.scrollIntoView({ block: 'center' });
    }
  }
  if (report && !state.busy) message(error.message, true);
}

function shareMessage(text) {
  $('share-message').textContent = text;
  $('share-message').hidden = !text;
}

function clearShare() {
  ++shareRequest;
  shareMessage('');
}

function readParameter(field) {
  const input = $(`param-${field.key}`);
  if (field.type === 'list') {
    const text = input.value.trim();
    let numbers;
    try { numbers = text.startsWith('[') ? JSON.parse(text) : text.split(',').map(value => value.trim() === '' ? NaN : Number(value)); }
    catch { throw parameterError(field, 'enter numbers separated by commas.'); }
    if (!Array.isArray(numbers) || !numbers.length || numbers.length > 16 || numbers.some(number => typeof number !== 'number' || !Number.isFinite(number))) throw parameterError(field, 'enter 1 to 16 numbers separated by commas.');
    return numbers;
  }
  const value = input.value.trim() === '' ? NaN : Number(input.value);
  if (!Number.isFinite(value)) throw parameterError(field, 'enter a number.');
  if (field.type === 'integer' && !Number.isInteger(value)) throw parameterError(field, 'enter a whole number.');
  return value;
}

function readParameters() {
  const parameters = Object.fromEntries(state.item.parameters.map(field => [field.key, readParameter(field)]));
  return dimensionParameters(state.item, parameters);
}

function parameterText(value) {
  return Array.isArray(value) ? value.join(', ') : String(value);
}

function fieldReverts() {
  for (const field of state.item?.parameters || []) {
    const note = $(`preview-field-${field.key}`), button = $(`revert-field-${field.key}`);
    if (!note || !button) continue;
    const preview = state.previewParameters?.[field.key];
    let changed = preview !== undefined;
    if (changed) {
      try { changed = JSON.stringify(readParameter(field)) !== JSON.stringify(preview); }
      catch { /* Invalid drafts can also return to a verified value. */ }
    }
    note.parentElement.hidden = !changed;
    note.textContent = changed ? `Preview: ${parameterText(preview)}${field.unit ? ` ${field.unit}` : ''}` : '';
    button.disabled = state.busy || !changed;
  }
}

function formValues() {
  return Object.fromEntries(state.item.parameters.map(field => [field.key, $(`param-${field.key}`).value]));
}

function sameParameters(a, b) {
  if (a === b) return true;
  if (!a || !b) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.hasOwn(b, key) && JSON.stringify(a[key]) === JSON.stringify(b[key]));
}

function setDownloads(matches = false) {
  const available = !!state.blob && matches && !state.busy;
  $('download').disabled = !available || state.item.kind === 'assembly';
  $('download-cad').disabled = !available;
  const retryFocused = document.activeElement === $('retry-original');
  $('original-recovery').hidden = !!state.blob;
  $('retry-original').disabled = state.busy;
  if (state.blob && retryFocused) {
    const input = $('parameter-fields').querySelector('input');
    input?.focus();
    input?.scrollIntoView({ block: 'center' });
  }
}

function cadButton() {
  $('download-cad').innerHTML = `${state.item.kind === 'assembly' ? 'Download parts kit' : 'Download CAD files'} <span>↓</span>`;
}

function setBusy(busy) {
  const focused = document.activeElement;
  const restoreFocus = !busy && focused === $('stop-build') && buildFocus?.item === state.item;
  if (busy) buildFocus = { element: focused, item: state.item };
  if (busy) { clearShare(); clearDimensionsError(); clearTransfer(); supersedeVersionRead(); }
  state.busy = busy;
  state.restoring = false;
  $('rebuild').disabled = busy;
  $('stop-build').hidden = !busy;
  $('revert-parameters').disabled = busy;
  $('save-dimensions').disabled = $('load-dimensions').disabled = busy;
  $('save-version').disabled = busy;
  versionControls();
  fieldReverts();
  if (!state.previewParameters) $('revert-parameters').hidden = true;
  setDownloads();
  if (busy && dialog.open && focused.disabled) $('stop-build').focus();
  if (restoreFocus) {
    const { element, item } = buildFocus;
    const epoch = state.epoch;
    // Download controls become enabled later in the request's completion handler.
    queueMicrotask(() => {
      if (state.busy || epoch !== state.epoch || item !== state.item || !dialog.open ||
          ![document.body, $('stop-build')].includes(document.activeElement)) return;
      (element.isConnected && !element.disabled && element.getClientRects().length ? element : $('rebuild')).focus();
    });
  }
}

function stopWaiting(timedOut = false) {
  if (!state.busy) return;
  const restoring = state.restoring;
  clearShare();
  abort?.abort();
  ++state.epoch;
  clearTransfer();
  setBusy(false);
  $('preview-loading').hidden = true;
  cadButton();
  markDirty();
  if (!state.blob) {
    previewDisplay(false);
  }
  const retained = state.blob ? 'Your preview and edits are kept.' : 'Your edits are kept.';
  message(`${timedOut ? 'This request exceeded 15 minutes.' : 'Stopped waiting.'} ${retained}${restoring ? '' : ' The service may still finish this request.'}${timedOut ? ' Try again later.' : ''}`, timedOut);
}

function markDirty(report = true) {
  rememberDraft();
  clearFieldErrors();
  try {
    state.parameters = readParameters();
    const stale = !sameParameters(state.parameters, state.previewParameters);
    $('revert-parameters').hidden = !state.previewParameters || !stale;
    setDownloads(!stale);
    $('mesh-status').textContent = !state.blob ? ($('preview-loading').hidden ? 'Preview unavailable' : 'Loading preview') : stale ? 'Update preview to apply edits' : sameParameters(state.previewParameters, state.item.defaults) ? 'Original dimensions' : 'Customized dimensions';
    if (report && !state.busy) message(!state.blob ? 'Update preview to load this model.' : stale ? 'Your edits are ready. Update the preview to build this version.' : 'Preview matches these parameters.');
    return !!state.blob && !stale;
  } catch (error) {
    $('revert-parameters').hidden = !state.previewParameters;
    setDownloads();
    $('mesh-status').textContent = 'Fix invalid dimensions';
    invalidParameters(error, false, report);
    return false;
  } finally {
    fieldReverts();
    updatePrinterFit();
  }
}

function rememberDraft() {
  if (!dialog.open || !activeEntry || activeEntry.model !== state.item?.name) return;
  const kept = saveDraft(activeEntry.id, state.item, formValues());
  const text = kept ? 'Edits stay in this tab after a refresh. Save dimensions to keep a file.' : 'Draft recovery is unavailable. Save valid dimensions to keep a file.';
  if ($('draft-note').textContent !== text) $('draft-note').textContent = text;
}

function parameterHint(field) {
  const unit = field.unit ? ` ${field.unit}` : '';
  const limits = field.min !== undefined && field.max !== undefined ? `Input range: ${field.min} to ${field.max}${unit}.`
    : field.min !== undefined ? `Minimum: ${field.min}${unit}.`
    : field.max !== undefined ? `Maximum: ${field.max}${unit}.` : '';
  if (field.type === 'list') return `1 to 16 numbers, separated by commas; order is kept.${limits ? ' ' + limits : ''}`;
  return `${field.type === 'integer' ? 'Whole numbers. ' : ''}${limits || 'Checked with related dimensions.'}`;
}

function fields(parameters) {
  clearShare();
  clearDimensionsError();
  $('parameter-fields').innerHTML = state.item.parameters.map(field => `<div class="parameter ${field.type === 'list' ? 'list' : ''}"><label for="param-${field.key}">${escape(field.label)}<span>${escape(field.unit)}</span></label><input id="param-${field.key}" data-parameter="${field.key}" aria-describedby="help-${field.key} error-${field.key} preview-field-${field.key}" ${field.type === 'list' ? 'type="text"' : `type="number" step="${field.type === 'integer' ? 1 : 'any'}" min="${field.min ?? -1000}" max="${field.max ?? 1000}"`} value="${escape(parameterText(parameters[field.key]))}" required><small id="help-${field.key}" class="parameter-help">${escape(parameterHint(field))}</small><small id="error-${field.key}" class="parameter-error" hidden></small><div class="parameter-preview" hidden><small id="preview-field-${field.key}"></small><button id="revert-field-${field.key}" data-revert-parameter="${field.key}" type="button" class="text-button" aria-label="Revert ${escape(field.label)} to preview" aria-describedby="preview-field-${field.key}" disabled>Revert value</button></div></div>`).join('');
  fieldReverts();
}

function checkMetadata(metadata, parameters) {
  if (!metadata || metadata.model !== state.item.name || metadata.units !== 'mm' ||
      metadata.printable !== (state.item.kind === 'print') || !sameParameters(metadata.parameters, parameters) ||
      !Array.isArray(metadata.bounds_mm) || metadata.bounds_mm.length !== 3 || metadata.bounds_mm.some(value => !Number.isFinite(value) || value <= 0)) {
    throw new Error('The model details do not match this request. Update the preview to try again.');
  }
}

async function sha256(buffer) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buffer)), byte => byte.toString(16).padStart(2, '0')).join('');
}

const validHash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const mediaType = response => response.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase();

function discardResponse(response) {
  if (!response?.bodyUsed) response?.body?.cancel?.().catch(() => {});
}

function previewDisplay(ready, loading = false) {
  $('viewer').setAttribute('aria-busy', String(loading));
  const canvas = $('viewer').querySelector('canvas');
  if (!ready && document.activeElement === canvas) {
    const input = $('parameter-fields').querySelector('input');
    input?.focus({ preventScroll: true });
    input?.scrollIntoView({ block: 'center' });
  }
  $('fallback-image').hidden = ready;
  document.querySelector('.view-tools').hidden = !ready;
  document.querySelector('.viewer-help').textContent = ready ? 'Drag to orbit · Scroll to zoom · Right-drag to pan. Focus preview: arrows pan, Shift + arrows orbit, + / − zoom, Home fits.' : loading ? 'Loading 3D preview. The catalog image shows original dimensions.' : '3D preview is unavailable. The catalog image shows original dimensions.';
  $('preview-badge').textContent = ready ? (state.item.kind === 'assembly' ? 'Reference assembly' : '3D preview') : 'Original catalog image';
  if (state.item.kind === 'print') $('download-note').textContent = ready ? 'The downloaded STL is the exact mesh in your preview.' : 'The verified STL uses the mesh dimensions shown here. The image shows the original model.';
}

function updateViewer(buffer, module) {
  if (!dialog.open || state.buffer !== buffer) return;
  try {
    if (!viewer && module) viewer = new module.ModelViewer($('viewer'), () => {
      if (dialog.open && state.buffer) previewDisplay(!!viewer && viewer.available);
    });
    viewer?.load(buffer, state.item.kind === 'assembly');
  } catch {
    viewer?.dispose();
    viewer = null;
    viewerPromise = Promise.resolve(null);
  }
  $('wireframe').setAttribute('aria-pressed', String(viewer?.wireframe || false));
  previewDisplay(!!viewer && viewer.available);
}

async function displayMesh(buffer, metadata, parameters, epoch, preserveFileError = false) {
  if (epoch !== state.epoch) return;
  checkMetadata(metadata, parameters);
  // Both static and regenerated meshes must match their advertised hash.
  const digest = await sha256(buffer);
  if (epoch !== state.epoch) return;
  if (digest !== metadata.mesh_sha256) throw new Error('The mesh transfer could not be verified. Update the preview to try again.');
  const meshSize = verifyMesh(buffer, metadata.bounds_mm);
  state.blob = new Blob([buffer], { type: 'model/stl' });
  state.buffer = buffer;
  state.meshSize = meshSize;
  state.metadata = metadata;
  state.cad = null;
  state.previewParameters = structuredClone(parameters);
  $('model-size').textContent = sizeText(metadata.bounds_mm);
  $('preview-loading').hidden = true;
  $('wireframe').setAttribute('aria-pressed', 'false');
  // A late original preview must not dismiss a newer rejected dimensions file.
  markDirty(!preserveFileError || $('dimensions-error').hidden);
  // Verified files are ready independently of the optional 3D module. Tie its
  // late result to the current mesh, including while a CAD export is running.
  if (viewer) updateViewer(buffer);
  else {
    previewDisplay(false, true);
    viewerPromise ||= import('./viewer.js').catch(() => null);
    viewerPromise.then(module => updateViewer(buffer, module));
  }
}

async function openModel(name, suppliedParameters, { navigation = true, saved, parameterError, fromFile = false } = {}) {
  const item = state.models.find(model => model.name === name);
  if (!item) return;
  supersedeVersionRead();
  $('link-notice').hidden = true;
  if (navigation) rememberPage(true);
  abort?.abort();
  const controller = abort = new AbortController();
  const epoch = ++state.epoch;
  clearTransfer();
  state.item = item;
  state.blob = state.buffer = state.meshSize = state.previewParameters = state.metadata = state.cad = null;
  state.parameters = structuredClone(item.defaults);
  let sharedError = parameterError;
  if (suppliedParameters !== undefined) {
    try { state.parameters = dimensionParameters(item, suppliedParameters); }
    catch (error) { sharedError = error.message; }
  }
  const linkedParameters = suppliedParameters !== undefined && !sharedError ? state.parameters : null;
  setBusy(false);
  cadButton();
  $('model-title').textContent = item.title;
  $('model-category').textContent = item.category;
  $('model-size').textContent = sizeText(item.bounds_mm);
  $('preview-badge').textContent = item.kind === 'assembly' ? 'Reference assembly' : '3D preview';
  $('reference-note').hidden = item.kind !== 'assembly';
  $('download').hidden = item.kind === 'assembly';
  $('cad-note').textContent = item.kind === 'assembly' ? 'Kit ZIP includes fitted STEP, STL, and 3MF for each part, quantities, saved dimensions, source, and the reference STEP.' : 'CAD ZIP includes STEP, 3MF, the preview STL, saved dimensions, and source.';
  $('download-note').textContent = item.kind === 'assembly' ? 'Print the kit components separately in their saved bed orientation. The assembled arrangement is for reference.' : 'The downloaded STL is the exact mesh in your preview.';
  $('fallback-image').src = item.image;
  $('fallback-image').hidden = true;
  $('preview-loading').hidden = false;
  $('viewer').setAttribute('aria-busy', 'true');
  $('preview-loading').textContent = 'Loading your part…';
  $('mesh-status').textContent = 'Loading preview';
  document.querySelector('.view-tools').hidden = true;
  document.querySelector('.viewer-help').textContent = 'Loading the original model. The catalog image shows original dimensions.';
  $('original-files').innerHTML = `${item.kind === 'print' ? `<a href="${item.mesh}" download>Original STL ↓</a><a href="/models/${item.name}.3mf" download>Original 3MF ↓</a>` : ''}<a href="/models/${item.name}.step" download>Original STEP ↓</a><a href="${item.source}" target="_blank">Python source ↗</a>`;
  $('parts').hidden = !item.parts.length;
  $('part-links').innerHTML = item.kit.map(part => `<button data-part="${part.model}">${escape(state.models.find(model => model.name === part.model).title)} ${part.role === 'fit_coupon' ? '· Fit coupon' : `× ${part.quantity}`} ↗</button>`).join('');
  fields(state.parameters);
  if (saved?.model === name) {
    for (const field of item.parameters) if (Object.hasOwn(saved.values, field.key)) $(`param-${field.key}`).value = saved.values[field.key];
  }
  const initialRead = dimensionsRead, initialValues = JSON.stringify(formValues());
  originalFeedback = () => {
    if (dimensionsRead !== initialRead || JSON.stringify(formValues()) !== initialValues) return;
    if (sharedError && saved?.model !== name) message(`Shared dimensions could not be applied. Original dimensions are shown. ${sharedError}`, true);
    else if (linkedParameters && !$('form-message').classList.contains('error') && sameParameters(state.parameters, linkedParameters) && !sameParameters(state.parameters, item.defaults)) message('Shared dimensions loaded. Update the preview to build this version.');
    else if (saved?.recovered && !$('form-message').classList.contains('error')) message(sameParameters(state.parameters, state.previewParameters) ? 'Your tab’s measurements were restored and match this preview.' : 'Your tab’s measurements were restored. Update the preview to build this version.');
  };
  message('Loading the original model…');
  viewer?.clear();
  if (!dialog.open) dialog.showModal();
  if (fromFile) {
    dimensionsLoaded();
    $('parameter-fields').querySelector('input')?.focus();
  }
  const url = new URL(location.href);
  url.searchParams.set('model', name);
  if (suppliedParameters !== undefined && !sharedError) url.searchParams.set('p', JSON.stringify(state.parameters)); else url.searchParams.delete('p');
  if (navigation) navigationURL(url, true);
  else if (saved || sharedError) {
    try {
      const parameters = readParameters();
      if (sameParameters(parameters, item.defaults)) url.searchParams.delete('p');
      else url.searchParams.set('p', JSON.stringify(parameters));
      navigationURL(url);
    } catch { /* Keep the invalid draft visible without encoding it in the URL. */ }
  }
  markDirty(false);
  await loadOriginal(item, controller, epoch, { saved, feedback: originalFeedback });
}

async function loadOriginal(item, controller, epoch, { saved, feedback, reload = false } = {}) {
  const initialRead = dimensionsRead, initialValues = JSON.stringify(formValues());
  const initialCurrent = () => epoch === state.epoch && dimensionsRead === initialRead && JSON.stringify(formValues()) === initialValues;
  let transfer;
  try {
    if (saved?.buffer && saved.metadata && saved.previewParameters) {
      await displayMesh(saved.buffer, saved.metadata, saved.previewParameters, epoch, true);
      if (epoch !== state.epoch) return;
      state.cad = saved.cad || null;
      return;
    }
    const buffer = await readOriginal(item.mesh, controller.signal, bytes => {
      transfer ||= transferProgress('original preview', epoch);
      if (bytes) transfer.receive(bytes);
    }, reload);
    transfer.verify();
    await displayMesh(buffer, { model: item.name, parameters: item.defaults, bounds_mm: item.bounds_mm, mesh_sha256: item.mesh_sha256, units: 'mm', printable: item.kind === 'print' }, item.defaults, epoch, true);
    if (epoch !== state.epoch) return;
    if (loadedFileIsCurrent()) dimensionsLoaded();
    else feedback?.();
  } catch (error) {
    if (error.name === 'AbortError' || epoch !== state.epoch) return;
    $('preview-loading').hidden = true;
    previewDisplay(false);
    try { readParameters(); $('mesh-status').textContent = 'Preview unavailable'; }
    catch { $('mesh-status').textContent = 'Fix invalid dimensions'; }
    if (loadedFileIsCurrent()) message(`Saved dimensions loaded. ${error.message} Update the preview to build this version.`, true);
    else if (initialCurrent() && $('dimensions-error').hidden) message(error.message, true);
  } finally {
    transfer?.finish();
  }
}

function retryOriginal() {
  if (!dialog.open || state.busy || state.blob) return;
  clearShare();
  const fromFile = loadedFileIsCurrent();
  abort?.abort();
  const controller = abort = new AbortController();
  const epoch = ++state.epoch;
  clearTransfer();
  if (fromFile) appliedDimensions.epoch = epoch;
  $('preview-loading').hidden = false;
  $('preview-loading').textContent = 'Loading your part…';
  previewDisplay(false, true);
  markDirty(false);
  if (fromFile) dimensionsLoaded();
  else if ($('dimensions-error').hidden) message('Loading the original model…');
  loadOriginal(state.item, controller, epoch, { feedback: originalFeedback, reload: true });
}

function cachedFiles(parameters, meshHash) {
  const saved = [...savedPages.values()].reverse().find(page => page.buffer &&
    page.metadata?.format === 'stl' && page.metadata.model === state.item.name &&
    (page.cad || !cadMismatches.has(page.metadata)) &&
    sameParameters(page.previewParameters, parameters) && (!meshHash || page.cad && page.metadata.mesh_sha256 === meshHash));
  return saved && { buffer: saved.buffer, metadata: saved.metadata, cad: saved.cad || null };
}

async function rebuild(event) {
  event?.preventDefault();
  if (state.busy) return;
  let parameters;
  try { parameters = readParameters(); }
  catch (error) { invalidParameters(error, true); return; }
  // Supersede any original preview that is still being fetched or initialized.
  abort?.abort();
  const controller = abort = new AbortController();
  const epoch = ++state.epoch;
  let succeeded = false;
  let response;
  let transfer;
  setBusy(true);
  state.parameters = parameters;
  $('preview-loading').hidden = !!state.blob;
  $('preview-loading').textContent = 'Building your part…';
  message('Building your CAD model… This can take a little longer after the service has been idle.');
  const timer = setTimeout(() => { if (state.busy && epoch === state.epoch) message('Still building. The CAD service may be starting; your request is running.'); }, 15000);
  const deadline = setTimeout(() => { if (epoch === state.epoch) stopWaiting(true); }, BUILD_WAIT_MS);
  try {
    const cached = cachedFiles(parameters);
    if (cached) {
      state.restoring = true;
      clearTimeout(timer);
      message('Restoring your previously verified preview…');
      $('preview-loading').textContent = 'Restoring your preview…';
      await displayMesh(cached.buffer, cached.metadata, parameters, epoch);
      if (epoch !== state.epoch) return;
      state.cad = cached.cad;
      const url = new URL(location.href);
      url.searchParams.set('p', JSON.stringify(parameters));
      navigationURL(url);
      succeeded = true;
      return;
    }
    response = await fetch('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: state.item.name, parameters }), signal: controller.signal });
    if (epoch !== state.epoch) return;
    if (!response.ok) {
      clearTimeout(timer);
      $('preview-loading').textContent = 'Reading service details…';
      message('The build request failed. Reading service details…');
      throw new Error(await responseProblem(response, controller.signal, 'The CAD service could not finish this build. Try again.'));
    }
    let metadata;
    try { metadata = JSON.parse(decodeURIComponent(response.headers.get('X-Model-Metadata'))); }
    catch { throw new Error('The CAD service returned unreadable model details. Update the preview to try again.'); }
    checkMetadata(metadata, parameters);
    if (metadata.format !== 'stl' || !validHash(metadata.mesh_sha256)) throw new Error('The CAD service returned unreadable model details. Update the preview to try again.');
    if (mediaType(response) !== 'model/stl') throw new Error('The CAD service returned an unreadable preview. Update the preview to try again.');
    clearTimeout(timer);
    message('Receiving your preview file…');
    $('preview-loading').textContent = 'Receiving your preview…';
    transfer = transferProgress('preview file', epoch);
    const buffer = await readFile(response, controller.signal, MAX_FILE_BYTES, transfer.receive);
    if (epoch !== state.epoch) return;
    transfer.verify();
    message('Verifying the preview file…');
    $('preview-loading').textContent = 'Verifying your preview…';
    await displayMesh(buffer, metadata, parameters, epoch);
    if (epoch !== state.epoch) return;
    const url = new URL(location.href);
    url.searchParams.set('p', JSON.stringify(parameters));
    navigationURL(url);
    succeeded = true;
  } catch (error) {
    if (error.name !== 'AbortError' && epoch === state.epoch) message(error.message, true);
  } finally {
    transfer?.finish();
    discardResponse(response);
    clearTimeout(timer);
    clearTimeout(deadline);
    if (epoch === state.epoch) {
      setBusy(false);
      $('preview-loading').hidden = true;
      if (succeeded) {
        if (markDirty()) message(state.item.kind === 'assembly' ? 'Preview updated. Explore the printable parts below.' : 'Preview updated. Your STL is ready.');
      }
      // Keep errors visible; enable downloading only if the current edits match the mesh.
      else {
        if (!state.blob) previewDisplay(false);
        markDirty(false);
      }
    }
  }
}

function downloadBase(fileHash) {
  if (sameParameters(state.previewParameters, state.item.defaults)) return state.item.name;
  const dimensions = sizeText(state.metadata.bounds_mm).replaceAll(' × ', 'x');
  return `${state.item.name}-custom-${dimensions}mm-${fileHash.slice(0, 12)}`;
}

function saveDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function loadedFileIsCurrent() {
  return dialog.open && appliedDimensions?.epoch === state.epoch && appliedDimensions.read === dimensionsRead;
}

function dimensionsLoaded() {
  if (appliedDimensions?.name) {
    message(`Version “${appliedDimensions.name}” loaded. ${sameParameters(state.parameters, state.previewParameters) ? 'These dimensions match the verified preview.' : 'Update the preview to build this version.'}`);
    return;
  }
  message(sameParameters(state.parameters, state.previewParameters) ? 'Saved dimensions match the verified preview.' : 'Saved dimensions loaded. Update the preview to build this version.');
}

function versionControls() {
  const selected = versions.find(version => version.id === $('version-choice').value);
  $('load-version').disabled = state.busy || !selected;
  $('remove-version').disabled = state.busy || !selected;
  $('rename-version').disabled = state.busy || !selected;
  $('replace-version').disabled = state.busy || !selected || selected.dimensions.model !== state.item?.name;
  $('export-versions').disabled = state.busy || !versions.length;
  $('import-versions').disabled = state.busy;
  $('undo-version').disabled = state.busy || !versionUndo;
  $('undo-version').hidden = !versionUndo;
}

function editVersions(action) {
  let beforeText;
  const result = action({
    getItem(key) { beforeText = localStorage.getItem(key); return beforeText; },
    setItem(key, text) { localStorage.setItem(key, text); },
  });
  const before = readVersions({ getItem: () => beforeText }, state.models);
  const after = Array.isArray(result) ? result : result.records;
  const selected = $('version-choice').value;
  if (versionUndo && JSON.stringify(before) !== JSON.stringify(versionUndo.after)) {
    versionUndo = null;
    versionControls();
  }
  if (JSON.stringify(before) !== JSON.stringify(after)) versionUndo = { before, after: structuredClone(after), selected };
  return result;
}

function renderVersions(selected = $('version-choice').value) {
  $('versions-sync-message').textContent = '';
  $('versions-sync-message').classList.remove('error');
  $('versions-sync-message').hidden = true;
  $('version-choice').innerHTML = `<option value="">${versions.length ? 'Choose a saved version…' : 'No saved versions yet'}</option>` + versions.map(version => {
    const item = state.models.find(model => model.name === version.dimensions.model);
    return `<option value="${escape(version.id)}">${escape(version.name)} · ${escape(item.title)}</option>`;
  }).join('');
  $('version-choice').value = selected;
  versionControls();
}

function versionMessage(text, error = false) {
  $('version-message').textContent = text;
  $('version-message').classList.toggle('error', error);
}

function versionsSyncMessage(text, error = false) {
  $('versions-sync-message').textContent = text;
  $('versions-sync-message').classList.toggle('error', error);
  $('versions-sync-message').hidden = false;
}

function refreshVersions() {
  try { versions = readVersions(localStorage, state.models); renderVersions(); }
  catch (error) {
    versions = [];
    renderVersions();
    versionMessage(error.name === 'SecurityError' ? 'Saved versions are unavailable in this browser. Use Save dimensions to keep a file.' : error.message, true);
  }
}

function saveCurrentVersion() {
  if (state.busy || !state.item) return;
  supersedeVersionRead();
  let name, parameters;
  try { name = versionName($('version-name').value); }
  catch (error) {
    $('version-name').setAttribute('aria-invalid', 'true');
    versionMessage(error.message, true);
    $('version-name').focus();
    return;
  }
  try { parameters = readParameters(); }
  catch (error) { invalidParameters(error, true); return; }
  if (supersedeDimensionsRead()) markDirty();
  try {
    versions = editVersions(storage => saveVersion(storage, state.models, state.item, parameters, name));
    renderVersions(versions[0].id);
    $('version-name').value = '';
    $('version-name').setAttribute('aria-invalid', 'false');
    versionMessage(`Version “${name}” saved in this browser. Save dimensions keeps a portable file.`);
    message('Current dimensions saved as a named version.');
  } catch (error) {
    versionMessage(['SecurityError', 'QuotaExceededError'].includes(error.name) ? 'This version could not be saved in this browser. Use Save dimensions to keep a file.' : error.message, true);
  }
}

function versionBackupMessage(text, error = false) {
  $('version-backup-message').textContent = text;
  $('version-backup-message').classList.toggle('error', error);
}

function supersedeVersionRead() {
  ++versionsRead;
  if (versionsLoading) versionBackupMessage('Backup import stopped. Choose the file again to import its versions.');
  versionsLoading = false;
}

async function loadVersionBackup(file) {
  if (!file || state.busy) return;
  const epoch = state.epoch, read = ++versionsRead;
  const current = () => dialog.open && state.epoch === epoch && read === versionsRead && !state.busy;
  versionsLoading = true;
  versionBackupMessage('Reading the version backup…');
  try {
    if (file.size > MAX_VERSIONS_BYTES) throw new Error('The version backup exceeds 64 KiB. Choose an Everyday Prints versions backup.');
    let text, timer;
    const timedOut = new Error('Reading the version backup took too long. Choose it again.');
    const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(timedOut), 15000); });
    try { text = await Promise.race([file.text(), timeout]); }
    catch (error) {
      if (error === timedOut) throw error;
      throw new Error('The version backup could not be read. Choose it again.');
    } finally { clearTimeout(timer); }
    if (!current()) return;
    const result = editVersions(storage => importVersionBackup(storage, state.models, text));
    versions = result.records;
    renderVersions();
    versionBackupMessage(result.added ? `Imported ${result.added} ${result.added === 1 ? 'version' : 'versions'}.${result.skipped ? ` ${result.skipped} already saved.` : ''} Current measurements are kept.` : 'These versions are already saved. Current measurements are kept.');
  } catch (error) {
    if (current()) versionBackupMessage(['SecurityError', 'QuotaExceededError'].includes(error.name) ? 'The backup could not be imported. Browser storage is unavailable. Existing versions and measurements are kept.' : error.message, true);
  } finally {
    if (read === versionsRead) versionsLoading = false;
  }
}

async function applyDimensions(item, parameters, { read = ++dimensionsRead, name, versionId } = {}) {
  const epoch = state.epoch;
  if (item.name !== state.item.name) {
    appliedDimensions = { epoch: epoch + 1, read, name, versionId };
    await openModel(item.name, parameters, { fromFile: true });
    return;
  }
  fields(parameters);
  markDirty();
  rememberPage(true);
  appliedDimensions = { epoch, read, name, versionId };
  dimensionsLoaded();
  $('parameter-fields').querySelector('input')?.focus();
}

function supersedeDimensionsRead() {
  const pending = dimensionsLoading?.read === dimensionsRead && dimensionsLoading.epoch === state.epoch;
  const feedback = pending || !$('dimensions-error').hidden;
  if (pending) ++dimensionsRead;
  dimensionsLoading = null;
  clearDimensionsError();
  return feedback;
}

async function loadDimensions(file) {
  if (!file || state.busy) return;
  clearDimensionsError();
  clearShare();
  const epoch = state.epoch, read = ++dimensionsRead;
  dimensionsLoading = { epoch, read };
  const draft = JSON.stringify(formValues());
  const current = () => dialog.open && state.epoch === epoch && dimensionsRead === read && !state.busy && JSON.stringify(formValues()) === draft;
  try {
    if (file.size > MAX_DIMENSIONS_BYTES) throw new Error('The saved dimensions file exceeds 16 KiB. Choose a parameters.json file.');
    message('Loading saved dimensions…');
    let text;
    let timer;
    const timedOut = new Error('Reading the saved dimensions file took too long. Choose it again.');
    const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(timedOut), 15000); });
    try { text = await Promise.race([file.text(), timeout]); }
    catch (error) {
      if (error === timedOut) throw error;
      throw new Error('The saved dimensions file could not be read. Choose it again.');
    } finally { clearTimeout(timer); }
    if (!current()) return;
    const { item, parameters } = savedDimensions(text, state.models);
    await applyDimensions(item, parameters, { read });
  } catch (error) {
    if (current()) {
      const text = `Saved dimensions could not be loaded. ${error.message}`;
      $('dimensions-error').textContent = text;
      $('dimensions-error').hidden = false;
      message(text, true);
      $('dimensions-error').scrollIntoView({ block: 'nearest' });
    }
  } finally {
    if (dimensionsLoading?.read === read) dimensionsLoading = null;
  }
}

function saveCadDownload() {
  saveDownload(state.cad.blob, state.cad.filename);
  message(state.item.kind === 'assembly' ? 'Parts kit downloaded. Print the components separately using the listed quantities.' : 'CAD files downloaded with the preview dimensions.');
}

async function downloadCad() {
  if (state.busy || !state.blob || $('download-cad').disabled) return;
  let parameters;
  try { parameters = readParameters(); }
  catch (error) { message(error.message, true); return; }
  if (!sameParameters(parameters, state.previewParameters)) { markDirty(); return; }
  state.cad ||= cachedFiles(parameters, state.metadata.mesh_sha256)?.cad;
  if (state.cad) { saveCadDownload(); return; }
  if (state.metadata.format !== 'stl') {
    // Catalog STLs use the original exporter's tessellation. Refresh once so
    // the CAD ZIP can contain the exact live preview mesh at these dimensions.
    const refreshedEpoch = state.epoch + 1;
    await rebuild();
    if (state.epoch !== refreshedEpoch || state.metadata?.format !== 'stl' || !sameParameters(parameters, state.previewParameters)) return;
    try { if (!sameParameters(readParameters(), parameters)) return; }
    catch { return; }
    return downloadCad();
  }
  const model = state.item.name;
  const previewHash = state.metadata.mesh_sha256;
  abort?.abort();
  const controller = abort = new AbortController();
  const epoch = ++state.epoch;
  setBusy(true);
  $('download-cad').textContent = 'Building CAD files…';
  message('Building the CAD download with your preview dimensions…');
  const timer = setTimeout(() => { if (epoch === state.epoch) message('Still building your CAD files. The service may be starting.'); }, 15000);
  const deadline = setTimeout(() => { if (epoch === state.epoch) stopWaiting(true); }, BUILD_WAIT_MS);
  let response;
  let transfer;
  try {
    response = await fetch('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, parameters, format: 'cad' }), signal: controller.signal });
    if (epoch !== state.epoch) return;
    if (!response.ok) {
      clearTimeout(timer);
      $('download-cad').textContent = 'Reading service details…';
      message('The CAD download request failed. Reading service details…');
      throw new Error(await responseProblem(response, controller.signal, 'The CAD download could not be built. Try again.'));
    }
    let metadata;
    try { metadata = JSON.parse(decodeURIComponent(response.headers.get('X-Model-Metadata'))); }
    catch { throw new Error('The CAD service returned unreadable download details. Try again.'); }
    checkMetadata(metadata, parameters);
    if (state.item.kind === 'assembly' && (!Array.isArray(metadata.kit) || metadata.kit.length !== state.item.kit.length ||
        state.item.kit.some(part => !metadata.kit.some(saved => saved && saved.model === part.model && saved.quantity === part.quantity && saved.role === part.role)))) {
      throw new Error('The parts kit does not match this assembly. Try again.');
    }
    if (metadata.format !== 'cad' || metadata.mesh_sha256 !== previewHash) {
      if (metadata.format === 'cad' && validHash(metadata.mesh_sha256) && metadata.mesh_sha256 !== previewHash)
        cadMismatches.add(state.metadata);
      throw new Error('The CAD files do not match the preview. Update the preview and try again.');
    }
    verifyMesh(state.buffer, metadata.bounds_mm);
    if (!validHash(metadata.file_sha256)) throw new Error('The CAD download transfer could not be verified. Try again.');
    if (mediaType(response) !== 'application/zip') throw new Error('The CAD service returned an unreadable download. Try again.');
    clearTimeout(timer);
    $('download-cad').textContent = 'Receiving CAD files…';
    message('Receiving your CAD download…');
    transfer = transferProgress('CAD download', epoch);
    const buffer = await readFile(response, controller.signal, MAX_FILE_BYTES, transfer.receive);
    if (epoch !== state.epoch) return;
    transfer.verify();
    $('download-cad').textContent = 'Verifying CAD files…';
    message('Verifying the CAD download…');
    const signature = new Uint8Array(buffer, 0, Math.min(4, buffer.byteLength));
    if (signature.length !== 4 || signature[0] !== 80 || signature[1] !== 75 || signature[2] !== 3 || signature[3] !== 4 ||
        await sha256(buffer) !== metadata.file_sha256) throw new Error('The CAD download transfer could not be verified. Try again.');
    if (epoch !== state.epoch) return;
    if (!sameParameters(readParameters(), parameters)) {
      message('Dimensions changed while the CAD files were building. Update the preview, then download again.');
      return;
    }
    state.cad = { blob: new Blob([buffer], { type: 'application/zip' }),
      filename: `${downloadBase(metadata.file_sha256)}-${state.item.kind === 'assembly' ? 'kit' : 'cad'}.zip` };
    saveCadDownload();
  } catch (error) {
    if (error.name !== 'AbortError' && epoch === state.epoch) message(error.message, true);
  } finally {
    transfer?.finish();
    discardResponse(response);
    clearTimeout(timer);
    clearTimeout(deadline);
    if (epoch === state.epoch) {
      setBusy(false);
      cadButton();
      try { setDownloads(sameParameters(readParameters(), state.previewParameters)); }
      catch { setDownloads(); }
    }
  }
}

$('search').addEventListener('input', filter);
$('category').addEventListener('change', filter);
document.querySelectorAll('[data-kind]').forEach(button => button.addEventListener('click', () => {
  state.kind = button.dataset.kind;
  document.querySelectorAll('[data-kind]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  filter();
}));
$('reset-search').addEventListener('click', resetFilters);
$('empty-reset').addEventListener('click', resetFilters);
$('catalog').addEventListener('click', event => { const card = event.target.closest('[data-model]'); if (card) openModel(card.dataset.model); });
$('close-editor').addEventListener('click', closeEditor);
dialog.addEventListener('cancel', event => { event.preventDefault(); closeEditor(); });
dialog.addEventListener('close', () => {
  if (dialog.open) return;
  supersedeVersionRead();
  clearShare();
  abort?.abort();
  ++state.epoch;
  clearTransfer();
  state.blob = state.buffer = state.meshSize = state.metadata = state.previewParameters = state.cad = null;
  setBusy(false);
  $('viewer').setAttribute('aria-busy', 'false');
  viewer?.clear();
});
dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeEditor(); } });
$('parameters').addEventListener('input', () => { ++dimensionsRead; clearShare(); clearDimensionsError(); markDirty(); });
$('parameter-fields').addEventListener('click', event => {
  const button = event.target.closest('[data-revert-parameter]');
  if (!button || button.disabled || state.busy || !state.previewParameters) return;
  const field = state.item.parameters.find(field => field.key === button.dataset.revertParameter);
  if (!field) return;
  ++dimensionsRead;
  clearShare();
  clearDimensionsError();
  const input = $(`param-${field.key}`);
  input.value = parameterText(state.previewParameters[field.key]);
  markDirty();
  rememberPage(true);
  input.focus();
});
$('parameters').addEventListener('submit', rebuild);
printerInputs.forEach(input => input.addEventListener('input', savePrinterVolume));
$('apply-printer-volume').addEventListener('click', () => {
  try {
    applyPrinterVolume(readPrinterVolume(localStorage));
    printerSyncMessage('Saved build volume applied. Model measurements and files are kept.');
    printerInputs[0].focus();
  } catch (error) {
    printerSyncMessage(error.name === 'SecurityError' ? 'Saved printer settings are unavailable in this browser. Current build volume is kept. Try again.' : error.message, true, true);
  }
});
$('clear-printer').addEventListener('click', () => {
  printerInputs.forEach(input => { input.value = ''; });
  savePrinterVolume();
  printerInputs[0].focus();
});
$('stop-build').addEventListener('click', () => stopWaiting());
$('retry-original').addEventListener('click', retryOriginal);
$('reset-parameters').addEventListener('click', () => { ++dimensionsRead; fields(state.item.defaults); markDirty(); });
$('revert-parameters').addEventListener('click', () => {
  if (state.busy || !state.previewParameters) return;
  ++dimensionsRead;
  fields(state.previewParameters);
  markDirty();
  rememberPage(true);
  $('parameter-fields').querySelector('input')?.focus();
});
$('part-links').addEventListener('click', event => {
  const button = event.target.closest('[data-part]');
  if (!button) return;
  let parameters;
  try { parameters = readParameters(); } catch { parameters = state.item.defaults; }
  const part = state.models.find(model => model.name === button.dataset.part);
  const shared = Object.fromEntries(Object.keys(part.defaults).filter(key => Object.hasOwn(parameters, key)).map(key => [key, parameters[key]]));
  openModel(part.name, { ...part.defaults, ...shared });
});
$('download').addEventListener('click', () => {
  if (!state.blob || $('download').disabled) return;
  saveDownload(state.blob, `${downloadBase(state.metadata.mesh_sha256)}.stl`);
});
$('download-cad').addEventListener('click', downloadCad);
$('save-dimensions').addEventListener('click', () => {
  if (state.busy) return;
  supersedeDimensionsRead();
  try {
    const record = dimensionRecord(state.item, readParameters());
    saveDownload(new Blob([JSON.stringify(record, null, 2) + '\n'], { type: 'application/json' }), `${state.item.name}-dimensions.json`);
    message('Dimensions saved.');
  } catch (error) { invalidParameters(error, true); }
});
$('load-dimensions').addEventListener('click', () => { if (!state.busy) $('dimensions-file').click(); });
$('dimensions-file').addEventListener('change', event => {
  const file = event.target.files[0];
  event.target.value = '';
  loadDimensions(file);
});
$('save-version').addEventListener('click', saveCurrentVersion);
$('version-name').addEventListener('input', () => {
  $('version-name').setAttribute('aria-invalid', 'false');
  versionMessage('Save up to 20 named versions in this browser. Save dimensions keeps a portable file.');
});
$('version-name').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); saveCurrentVersion(); } });
$('version-choice').addEventListener('change', versionControls);
$('load-version').addEventListener('click', async () => {
  if (state.busy) return;
  supersedeVersionRead();
  const id = $('version-choice').value;
  try {
    versions = readVersions(localStorage, state.models);
    renderVersions(id);
    const version = versions.find(record => record.id === id);
    if (!version) throw new Error('This version is no longer saved. Choose another version.');
    supersedeDimensionsRead();
    clearShare();
    versionMessage(`Version “${version.name}” opened. Update preview to build changed dimensions.`);
    await applyDimensions(state.models.find(item => item.name === version.dimensions.model), version.dimensions.parameters, { name: version.name, versionId: version.id });
  } catch (error) {
    versionMessage(error.name === 'SecurityError' ? 'Saved versions are unavailable in this browser. Use Load dimensions to reopen a file.' : error.message, true);
  }
});
$('rename-version').addEventListener('click', () => {
  if (state.busy) return;
  supersedeVersionRead();
  let name;
  try { name = versionName($('version-name').value); }
  catch (error) {
    $('version-name').setAttribute('aria-invalid', 'true');
    versionMessage(error.message, true);
    $('version-name').focus();
    return;
  }
  const id = $('version-choice').value;
  try {
    versions = editVersions(storage => renameVersion(storage, state.models, id, name));
    renderVersions(id);
    if (appliedDimensions?.versionId === id) appliedDimensions.name = name;
    $('version-name').value = '';
    $('version-name').setAttribute('aria-invalid', 'false');
    versionMessage(`Version renamed to “${name}”. Its saved dimensions and your current measurements are kept.`);
  } catch (error) {
    versionMessage(['SecurityError', 'QuotaExceededError'].includes(error.name) ? 'This version could not be renamed. Browser storage is unavailable. Existing versions are kept.' : error.message, true);
  }
});
$('replace-version').addEventListener('click', () => {
  if (state.busy || !state.item) return;
  supersedeVersionRead();
  let parameters;
  try { parameters = readParameters(); }
  catch (error) { invalidParameters(error, true); return; }
  if (supersedeDimensionsRead()) markDirty();
  const id = $('version-choice').value;
  try {
    versions = editVersions(storage => replaceVersion(storage, state.models, id, state.item, parameters));
    renderVersions(id);
    const version = versions.find(record => record.id === id);
    versionMessage(`Dimensions replaced in “${version.name}”. ${sameParameters(parameters, state.previewParameters) ? 'These measurements match the verified preview.' : 'Update preview to build changed measurements.'}`);
  } catch (error) {
    versionMessage(['SecurityError', 'QuotaExceededError'].includes(error.name) ? 'Saved dimensions could not be replaced. Browser storage is unavailable. Existing versions are kept. Use Save dimensions to keep a file.' : error.message, true);
  }
});
$('remove-version').addEventListener('click', () => {
  if (state.busy) return;
  supersedeVersionRead();
  try {
    versions = editVersions(storage => removeVersion(storage, state.models, $('version-choice').value));
    renderVersions('');
    versionMessage('Version removed. Current measurements and files are kept.');
    $('version-choice').focus();
  } catch (error) {
    versionMessage(['SecurityError', 'QuotaExceededError'].includes(error.name) ? 'The version could not be removed. Browser storage is unavailable.' : error.message, true);
  }
});
$('undo-version').addEventListener('click', () => {
  if (state.busy || !versionUndo) return;
  supersedeVersionRead();
  try {
    const selected = versionUndo.selected;
    versions = undoVersionChange(localStorage, state.models, versionUndo);
    versionUndo = null;
    renderVersions(selected);
    const opened = versions.find(version => version.id === appliedDimensions?.versionId);
    if (opened) appliedDimensions.name = opened.name;
    versionMessage('Last version change undone. Current measurements and files are kept.');
    $('version-choice').focus();
  } catch (error) {
    if (error.versionsChanged) { versionUndo = null; refreshVersions(); $('version-choice').focus(); }
    versionMessage(['SecurityError', 'QuotaExceededError'].includes(error.name) ? 'Undo could not be saved. Browser storage is unavailable. Existing versions are kept. Try again or use Save dimensions to keep a file.' : error.message, true);
  }
});
$('export-versions').addEventListener('click', () => {
  if (state.busy) return;
  supersedeVersionRead();
  try {
    const text = versionBackup(localStorage, state.models);
    saveDownload(new Blob([text], { type: 'application/json' }), 'everyday-prints-versions.json');
    versionBackupMessage('Version backup exported. Keep this file to restore names and measurements in another browser.');
  } catch (error) {
    versionBackupMessage(error.name === 'SecurityError' ? 'Saved versions are unavailable in this browser.' : error.message, true);
  }
});
$('import-versions').addEventListener('click', () => { if (!state.busy) $('versions-file').click(); });
$('versions-file').addEventListener('change', event => {
  const file = event.target.files[0];
  event.target.value = '';
  loadVersionBackup(file);
});
$('share').addEventListener('click', async () => {
  if (supersedeDimensionsRead() && !state.busy) markDirty();
  clearShare();
  let parameters;
  try { parameters = readParameters(); }
  catch (error) { invalidParameters(error, true); return; }
  const epoch = state.epoch;
  const request = shareRequest;
  const current = () => {
    if (!dialog.open || epoch !== state.epoch || request !== shareRequest) return false;
    try { return sameParameters(parameters, readParameters()); } catch { return false; }
  };
  const url = new URL(location.href);
  url.searchParams.set('model', state.item.name);
  url.searchParams.set('p', JSON.stringify(parameters));
  // The address bar is also a usable fallback when clipboard access is denied.
  navigationURL(url);
  shareMessage('Copying link…');
  const timer = setTimeout(() => { if (current()) shareMessage('Copying is taking longer. Copy the page URL to share these dimensions.'); }, 3000);
  try {
    const copied = await copyLink(url.href);
    if (copied && current()) shareMessage('Link copied with these dimensions.');
  } catch { if (current()) shareMessage('Copy the page URL to share this model with these dimensions.'); }
  finally { clearTimeout(timer); }
});
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => viewer?.view(button.dataset.view)));
$('wireframe').addEventListener('click', () => $('wireframe').setAttribute('aria-pressed', String(viewer?.toggleWireframe() || false)));
document.addEventListener('keydown', event => { if (event.key === '/' && !dialog.open && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) { event.preventDefault(); $('search').focus(); } });

function catalogModels(data) {
  const models = data?.models;
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const identifier = value => typeof value === 'string' && /^[a-z][a-z0-9_]*$/.test(value);
  if (!Array.isArray(models) || !models.length) throw new Error('Invalid catalog.');
  for (const model of models) {
    if (!model || !identifier(model.name) || !['print', 'assembly'].includes(model.kind) ||
        !['title', 'category', 'image', 'mesh', 'source'].every(key => typeof model[key] === 'string' && model[key].length) ||
        !Number.isInteger(model.number) || model.number < 1 || !/^[a-f0-9]{64}$/.test(model.mesh_sha256) ||
        !Array.isArray(model.bounds_mm) || model.bounds_mm.length !== 3 || model.bounds_mm.some(value => !numeric(value) || value <= 0) ||
        !model.defaults || typeof model.defaults !== 'object' || Array.isArray(model.defaults) ||
        !Array.isArray(model.parameters) || !Array.isArray(model.parts) || !Array.isArray(model.kit) ||
        model.kit.length !== model.parts.length || new Set(model.kit.map(part => part?.model)).size !== model.parts.length ||
        model.kit.some(part => !part || !model.parts.includes(part.model) || !Number.isInteger(part.quantity) || part.quantity < 1 || part.quantity > 64 || !['component', 'fit_coupon'].includes(part.role))) throw new Error('Invalid catalog.');
    const keys = Object.keys(model.defaults);
    if (keys.length !== model.parameters.length || new Set(model.parameters.map(field => field?.key)).size !== keys.length ||
        !Object.values(model.defaults).every(value => Array.isArray(value) ? value.length > 0 && value.length <= 16 && value.every(numeric) : numeric(value))) throw new Error('Invalid catalog.');
    for (const field of model.parameters) {
      if (!field || !identifier(field.key) || !Object.hasOwn(model.defaults, field.key) ||
          !['number', 'integer', 'list'].includes(field.type) || typeof field.label !== 'string' || typeof field.unit !== 'string' ||
          !numeric(field.step) || field.step <= 0 || (field.type === 'list') !== Array.isArray(model.defaults[field.key]) ||
          (field.type === 'integer' && !Number.isInteger(model.defaults[field.key])) ||
          (field.min !== undefined && !numeric(field.min)) || (field.max !== undefined && !numeric(field.max))) throw new Error('Invalid catalog.');
    }
  }
  const names = new Map(models.map(model => [model.name, model]));
  if (names.size !== models.length || models.some(model => model.parts.some(name => names.get(name)?.kind !== 'print'))) throw new Error('Invalid catalog.');
  return models;
}

async function catalogResponse(signal) {
  signal.throwIfAborted();
  let stop;
  const interrupted = new Promise((_, reject) => {
    stop = () => reject(signal.reason);
    signal.addEventListener('abort', stop, { once: true });
  });
  try {
    const pending = fetch('/catalog.json', { signal, cache: 'no-cache' }).then(response => {
      if (signal.aborted) {
        discardResponse(response);
        signal.throwIfAborted();
      }
      return response;
    });
    return await Promise.race([pending, interrupted]);
  } finally {
    signal.removeEventListener('abort', stop);
  }
}

async function start() {
  if (state.catalogLoading) return;
  state.catalogLoading = true;
  $('catalog-loading').hidden = false;
  $('catalog-failure').hidden = true;
  $('empty').hidden = true;
  $('result-count').textContent = 'Loading…';
  $('catalog').setAttribute('aria-busy', 'true');
  $('retry-catalog').disabled = true;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  let response;
  try {
    response = await catalogResponse(controller.signal);
    if (!response.ok) throw new Error('Catalog unavailable.');
    const buffer = await readFile(response, controller.signal, MAX_CATALOG_BYTES);
    const models = catalogModels(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(buffer)));
    // Use stable file basenames as IDs, but index their words separately.
    const index = new MiniSearch({ idField: 'name', fields: ['title', 'words', 'tags', 'category', 'spec'] });
    index.addAll(models.map(model => ({ ...model, words: model.name.replaceAll('_', ' ') })));
    // Publish only a complete catalog, so a failed attempt cannot leave partial data.
    state.models = models;
    refreshVersions();
    searchIndex = index;
    const category = $('category').value;
    $('category').innerHTML = '<option value="">All categories</option>' + [...new Set(models.map(model => model.category))].map(category => `<option value="${escape(category)}">${escape(category)}</option>`).join('');
    $('category').value = category;
    document.querySelectorAll('[data-count]').forEach(element => { element.textContent = String(models.filter(model => model.kind === element.dataset.count).length); });
    filter();
  } catch {
    $('result-count').textContent = 'Unavailable';
    $('catalog-failure').hidden = false;
    $('catalog-error').textContent = 'The library could not be loaded. Try again.';
    return;
  } finally {
    discardResponse(response);
    clearTimeout(timer);
    state.catalogLoading = false;
    $('catalog-loading').hidden = true;
    $('catalog').setAttribute('aria-busy', 'false');
    $('retry-catalog').disabled = false;
  }
  await restoreLocation();
}
window.addEventListener('popstate', restoreLocation);
window.addEventListener('storage', syncPrinterVolume);
window.addEventListener('storage', event => {
  if (!state.models.length || (event.key !== VERSIONS_KEY && event.key !== null)) return;
  const focused = document.activeElement;
  try {
    if (event.storageArea !== localStorage) return;
    const next = readVersions(localStorage, state.models);
    const recovering = !$('versions-sync-message').hidden && $('versions-sync-message').classList.contains('error');
    if (JSON.stringify(next) === JSON.stringify(versions) && !recovering) return;
    versionUndo = null;
    versions = next;
    renderVersions();
    const opened = versions.find(version => version.id === appliedDimensions?.versionId);
    if (opened) appliedDimensions.name = opened.name;
    versionsSyncMessage(recovering ? 'Saved versions are available again. Current measurements are kept.' : 'Saved versions changed in another tab. Current measurements are kept.');
  } catch (error) {
    versionUndo = null;
    versions = [];
    renderVersions();
    versionsSyncMessage(error.name === 'SecurityError' ? 'Saved versions are unavailable in this browser. Current measurements are kept. Use Save dimensions to keep a file.' : `${error.message} Current measurements are kept.`, true);
  } finally {
    if (dialog.open && !state.busy && focused instanceof HTMLButtonElement && focused.disabled && focused.closest('.named-versions')) $('version-choice').focus();
  }
});
$('retry-catalog').addEventListener('click', start);
restorePrinterVolume();
start();
