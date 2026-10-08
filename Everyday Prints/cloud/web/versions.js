import { dimensionRecord } from './dimensions.js';

export const VERSIONS_KEY = 'everyday-prints-versions';
export const MAX_VERSIONS = 20;
export const MAX_VERSIONS_BYTES = 64 * 1024;

export function versionName(value) {
  const name = value.trim();
  if (!name || name.length > 80) throw new Error('Name your version using 1 to 80 characters.');
  return name;
}

function checkedVersions(records, models, requireIds = true) {
  const invalid = () => new Error('Saved versions could not be read. Use Load dimensions to reopen a saved file.');
  if (!Array.isArray(records) || records.length > MAX_VERSIONS) throw invalid();
  const ids = new Set();
  return records.map(record => {
    const item = models.find(model => model.name === record?.dimensions?.model);
    if (!item || (requireIds && (typeof record.id !== 'string' || !/^[a-f0-9-]{36}$/.test(record.id) || ids.has(record.id))) ||
        typeof record.name !== 'string' || record.name !== versionName(record.name) || record.dimensions.units !== 'mm' ||
        !record.dimensions.parameters || Object.keys(record.dimensions.parameters).length !== item.parameters.length) throw invalid();
    if (requireIds) ids.add(record.id);
    try { return { ...(requireIds ? { id: record.id } : {}), name: record.name, dimensions: dimensionRecord(item, record.dimensions.parameters) }; }
    catch { throw invalid(); }
  });
}

export function readVersions(storage, models) {
  const text = storage.getItem(VERSIONS_KEY);
  if (!text) return [];
  if (new TextEncoder().encode(text).byteLength > MAX_VERSIONS_BYTES) throw new Error('Saved versions exceed 64 KiB. Use Load dimensions to reopen a saved file.');
  let records;
  try { records = JSON.parse(text); } catch { throw new Error('Saved versions could not be read. Use Load dimensions to reopen a saved file.'); }
  return checkedVersions(records, models);
}

function writeVersions(storage, records) {
  const text = JSON.stringify(records);
  if (new TextEncoder().encode(text).byteLength > MAX_VERSIONS_BYTES) throw new Error('Saved versions are full. Remove a version or use Save dimensions to keep a file.');
  storage.setItem(VERSIONS_KEY, text);
  return records;
}

export function saveVersion(storage, models, item, parameters, label) {
  const name = versionName(label);
  const dimensions = dimensionRecord(item, parameters);
  const records = readVersions(storage, models);
  if (records.length >= MAX_VERSIONS) throw new Error('You have 20 saved versions. Remove one or use Save dimensions to keep a file.');
  if (records.some(record => record.dimensions.model === item.name && record.name.toLowerCase() === name.toLowerCase())) {
    throw new Error('This model already has a version with that name. Choose another name or remove the saved version.');
  }
  return writeVersions(storage, [{ id: crypto.randomUUID(), name, dimensions }, ...records]);
}

export function removeVersion(storage, models, id) {
  const records = readVersions(storage, models);
  if (!records.some(record => record.id === id)) throw new Error('This version is no longer saved. Choose another version.');
  return writeVersions(storage, records.filter(record => record.id !== id));
}

export function renameVersion(storage, models, id, label) {
  const name = versionName(label);
  const records = readVersions(storage, models);
  const selected = records.find(record => record.id === id);
  if (!selected) throw new Error('This version is no longer saved. Choose another version.');
  if (records.some(record => record.id !== id && record.dimensions.model === selected.dimensions.model && record.name.toLowerCase() === name.toLowerCase())) {
    throw new Error('This model already has a version with that name. Choose another name.');
  }
  if (selected.name === name) return records;
  return writeVersions(storage, records.map(record => record.id === id ? { ...record, name } : record));
}

export function replaceVersion(storage, models, id, item, parameters) {
  const records = readVersions(storage, models);
  const selected = records.find(record => record.id === id);
  if (!selected) throw new Error('This version is no longer saved. Choose another version.');
  if (selected.dimensions.model !== item.name) throw new Error('Open this version’s model before replacing its dimensions.');
  const dimensions = dimensionRecord(item, parameters);
  if (JSON.stringify(selected.dimensions.parameters) === JSON.stringify(dimensions.parameters)) return records;
  return writeVersions(storage, records.map(record => record.id === id ? { ...record, dimensions } : record));
}

export function undoVersionChange(storage, models, change) {
  const current = readVersions(storage, models);
  const before = checkedVersions(change?.before, models);
  const after = checkedVersions(change?.after, models);
  if (JSON.stringify(current) !== JSON.stringify(after)) {
    throw Object.assign(new Error('Saved versions changed since this action. Undo cannot replace newer versions.'), { versionsChanged: true });
  }
  return writeVersions(storage, before);
}

export function versionBackup(storage, models) {
  const versions = readVersions(storage, models).map(({ name, dimensions }) => ({ name, dimensions }));
  if (!versions.length) throw new Error('Save a named version before exporting a backup.');
  const text = JSON.stringify({ format: 'everyday-prints-versions', version: 1, versions }, null, 2) + '\n';
  if (new TextEncoder().encode(text).byteLength > MAX_VERSIONS_BYTES) throw new Error('The version backup exceeds 64 KiB. Save fewer versions in this backup.');
  return text;
}

export function importVersionBackup(storage, models, text) {
  if (new TextEncoder().encode(text).byteLength > MAX_VERSIONS_BYTES) throw new Error('The version backup exceeds 64 KiB. Choose an Everyday Prints versions backup.');
  let backup;
  try { backup = JSON.parse(text.replace(/^\uFEFF/, '')); }
  catch { throw new Error('The version backup is not valid JSON.'); }
  if (backup?.format !== 'everyday-prints-versions' || backup.version !== 1 || !Array.isArray(backup.versions) || !backup.versions.length) {
    throw new Error('Choose an Everyday Prints versions backup (version 1) containing named versions.');
  }
  let incoming;
  try { incoming = checkedVersions(backup.versions, models, false); }
  catch { throw new Error('The backup contains an unsupported model, name or measurement. Existing versions are kept.'); }
  const records = readVersions(storage, models);
  const working = [...records], added = [];
  let skipped = 0;
  for (const version of incoming) {
    let name = version.name, suffix = 2;
    for (;;) {
      const existing = working.find(record => record.dimensions.model === version.dimensions.model && record.name.toLowerCase() === name.toLowerCase());
      if (!existing) break;
      if (JSON.stringify(existing.dimensions.parameters) === JSON.stringify(version.dimensions.parameters)) { name = null; break; }
      const ending = ` (${suffix++})`;
      let base = version.name;
      while (base.length + ending.length > 80) base = [...base].slice(0, -1).join('');
      name = base.trimEnd() + ending;
    }
    if (name === null) { skipped++; continue; }
    if (working.length >= MAX_VERSIONS) throw new Error('This backup would exceed 20 saved versions. Remove versions before importing it. Existing versions are kept.');
    const record = { ...version, id: crypto.randomUUID(), name };
    working.push(record);
    added.push(record);
  }
  const merged = added.length ? writeVersions(storage, [...added, ...records]) : records;
  return { records: merged, added: added.length, skipped };
}
