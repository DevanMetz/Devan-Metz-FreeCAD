import { dimensionRecord } from './dimensions.js';

export const VERSIONS_KEY = 'everyday-prints-versions';
export const MAX_VERSIONS = 20;
const MAX_BYTES = 64 * 1024;

export function versionName(value) {
  const name = value.trim();
  if (!name || name.length > 80) throw new Error('Name your version using 1 to 80 characters.');
  return name;
}

export function readVersions(storage, models) {
  const text = storage.getItem(VERSIONS_KEY);
  if (!text) return [];
  const invalid = () => new Error('Saved versions could not be read. Use Load dimensions to reopen a saved file.');
  if (new TextEncoder().encode(text).byteLength > MAX_BYTES) throw invalid();
  let records;
  try { records = JSON.parse(text); } catch { throw invalid(); }
  if (!Array.isArray(records) || records.length > MAX_VERSIONS) throw invalid();
  const ids = new Set();
  return records.map(record => {
    const item = models.find(model => model.name === record?.dimensions?.model);
    if (!item || typeof record.id !== 'string' || !/^[a-f0-9-]{36}$/.test(record.id) || ids.has(record.id) ||
        typeof record.name !== 'string' || record.name !== versionName(record.name) || record.dimensions.units !== 'mm' ||
        !record.dimensions.parameters || Object.keys(record.dimensions.parameters).length !== item.parameters.length) throw invalid();
    ids.add(record.id);
    try { return { id: record.id, name: record.name, dimensions: dimensionRecord(item, record.dimensions.parameters) }; }
    catch { throw invalid(); }
  });
}

function writeVersions(storage, records) {
  const text = JSON.stringify(records);
  if (new TextEncoder().encode(text).byteLength > MAX_BYTES) throw new Error('Saved versions are full. Remove a version or use Save dimensions to keep a file.');
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
