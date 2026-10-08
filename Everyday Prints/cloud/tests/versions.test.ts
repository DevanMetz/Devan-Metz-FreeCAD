import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { MAX_VERSIONS, MAX_VERSIONS_BYTES, VERSIONS_KEY, importVersionBackup, readVersions, removeVersion, renameVersion, replaceVersion, saveVersion, versionBackup } from '../web/versions.js';

const cloud = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const models = JSON.parse(readFileSync(resolve(cloud, 'public/catalog.json'), 'utf8')).models;
const tray = models.find((item: any) => item.name === 'parts_tray');
function memory(text: string | null = null) {
  return { text, getItem(key: string) { assert.equal(key, VERSIONS_KEY); return this.text; },
    setItem(key: string, value: string) { assert.equal(key, VERSIONS_KEY); this.text = value; } };
}

test('renaming every catalog model retains its identity, dimensions and canonical assembly inventory', () => {
  for (const item of models) {
    const storage = memory();
    const original = saveVersion(storage, models, item, item.defaults, 'Original');
    const renamed = renameVersion(storage, models, original[0].id, ' Shelf <wide> 🧰 ');
    assert.deepEqual(renamed, [{ ...original[0], name: 'Shelf <wide> 🧰' }]);
    assert.deepEqual(readVersions(storage, models), renamed);
  }
});

test('replacing real decimal and list dimensions works in a full library without changing names, identities or order', () => {
  const storage = memory();
  const cable = models.find((item: any) => item.name === 'cable_comb');
  saveVersion(storage, models, cable, cable.defaults, 'Routing');
  for (let i = 0; i < 19; i++) saveVersion(storage, models, tray, tray.defaults, 'Tray ' + i);
  const original = readVersions(storage, models);
  for (const item of [tray, cable]) {
    const selected = original.find((record: any) => record.dimensions.model === item.name)!;
    const exported = JSON.parse(readFileSync(resolve(cloud, '../review/cloud_export_samples', item.name, 'parameters.json'), 'utf8'));
    const before = readVersions(storage, models);
    const updated = replaceVersion(storage, models, selected.id, item, exported.parameters);
    assert.equal(updated.length, MAX_VERSIONS);
    assert.deepEqual(updated.map((record: any) => [record.id, record.name]), original.map((record: any) => [record.id, record.name]));
    assert.deepEqual(updated.find((record: any) => record.id === selected.id)?.dimensions.parameters, exported.parameters);
    assert.deepEqual(updated.filter((record: any) => record.id !== selected.id), before.filter((record: any) => record.id !== selected.id));
    assert.equal(Object.hasOwn(updated.find((record: any) => record.id === selected.id)!.dimensions, 'mesh_sha256'), false);
  }
  const source = readVersions(storage, models);
  const restored = importVersionBackup(memory(), models, versionBackup(storage, models)).records;
  assert.deepEqual(restored.map(({ name, dimensions }: any) => ({ name, dimensions })), source.map(({ name, dimensions }: any) => ({ name, dimensions })));
});

test('rename checks fresh model-specific name conflicts and replacement preserves entries from another view', () => {
  const storage = memory();
  const selected = saveVersion(storage, models, tray, tray.defaults, 'First')[0];
  const cable = models.find((item: any) => item.name === 'cable_comb');
  saveVersion(storage, models, cable, cable.defaults, 'Other');
  const before = saveVersion(storage, models, tray, tray.defaults, 'Second');
  const text = storage.text;
  for (const name of ['', ' ', 'x'.repeat(81), ' SECOND ']) assert.throws(() => renameVersion(storage, models, selected.id, name));
  assert.equal(storage.text, text);
  const renamed = renameVersion(storage, models, selected.id, 'Other');
  assert.deepEqual(renamed.filter((record: any) => record.id !== selected.id), before.filter((record: any) => record.id !== selected.id));
  const newest = saveVersion(storage, models, tray, tray.defaults, 'New elsewhere');
  const updated = replaceVersion(storage, models, selected.id, tray, { ...tray.defaults, length: 180.555 });
  assert.deepEqual(updated.filter((record: any) => record.id !== selected.id), newest.filter((record: any) => record.id !== selected.id));
  removeVersion(storage, models, selected.id);
  const remaining = storage.text;
  assert.throws(() => renameVersion(storage, models, selected.id, 'Missing'), /no longer saved/);
  assert.throws(() => replaceVersion(storage, models, selected.id, tray, tray.defaults), /no longer saved/);
  assert.equal(storage.text, remaining);
});

test('invalid measurements, cross-model replacements and unreadable storage cannot change saved entries', () => {
  const storage = memory();
  const selected = saveVersion(storage, models, tray, tray.defaults, 'Original')[0];
  const text = storage.text;
  const cable = models.find((item: any) => item.name === 'cable_comb');
  assert.throws(() => replaceVersion(storage, models, selected.id, cable, cable.defaults), /Open this version/);
  for (const parameters of [{ ...tray.defaults, length: NaN }, { ...tray.defaults, length: 1001 }, { ...tray.defaults, length: '180' }, { ...tray.defaults, columns: 1.5 }, { ...tray.defaults, unknown: 5 }]) {
    assert.throws(() => replaceVersion(storage, models, selected.id, tray, parameters));
  }
  assert.equal(storage.text, text);
  for (const corrupted of ['broken', '{}', JSON.stringify([selected, selected])]) {
    storage.text = corrupted;
    assert.throws(() => renameVersion(storage, models, selected.id, 'Changed'));
    assert.throws(() => replaceVersion(storage, models, selected.id, tray, tray.defaults));
    assert.equal(storage.text, corrupted);
  }
});

test('failed writes keep old versions while unchanged rename and replacement work without a storage write', () => {
  const storage = memory();
  const original = saveVersion(storage, models, tray, tray.defaults, 'Original');
  const text = storage.text;
  let writes = 0;
  storage.setItem = () => { writes++; throw new DOMException('Full', 'QuotaExceededError'); };
  assert.deepEqual(renameVersion(storage, models, original[0].id, ' Original '), original);
  assert.deepEqual(replaceVersion(storage, models, original[0].id, tray, tray.defaults), original);
  assert.equal(writes, 0);
  assert.throws(() => renameVersion(storage, models, original[0].id, 'Changed'), /Full/);
  assert.throws(() => replaceVersion(storage, models, original[0].id, tray, { ...tray.defaults, length: 180.5 }), /Full/);
  assert.equal(storage.text, text);
  storage.getItem = () => { throw new DOMException('Denied', 'SecurityError'); };
  assert.throws(() => renameVersion(storage, models, original[0].id, 'Changed'), /Denied/);
  assert.throws(() => replaceVersion(storage, models, original[0].id, tray, tray.defaults), /Denied/);
});

test('all 53 models retain exact default dimensions and canonical kit quantities as named versions', () => {
  assert.equal(models.length, 53);
  for (const item of models) {
    const storage = memory();
    const saved = saveVersion(storage, models, item, item.defaults, 'Original');
    const restored = readVersions(storage, models);
    assert.deepEqual(restored, saved);
    assert.deepEqual(restored[0].dimensions.parameters, item.defaults);
    if (item.kind === 'assembly') assert.deepEqual(restored[0].dimensions.kit, item.kit);
  }
});

test('real exported decimal and list measurements round-trip independently of file geometry metadata', () => {
  for (const name of ['parts_tray', 'cable_comb']) {
    const item = models.find((item: any) => item.name === name);
    const record = JSON.parse(readFileSync(resolve(cloud, '../review/cloud_export_samples', name, 'parameters.json'), 'utf8'));
    const storage = memory();
    saveVersion(storage, models, item, record.parameters, 'Kitchen <wide> ✓');
    assert.deepEqual(readVersions(storage, models)[0].dimensions.parameters, record.parameters);
    const raw = JSON.parse(storage.text!);
    raw[0].dimensions.bounds_mm = [999, 999, 999];
    raw[0].dimensions.mesh_sha256 = 'untrusted';
    storage.text = JSON.stringify(raw);
    assert.equal(Object.hasOwn(readVersions(storage, models)[0].dimensions, 'bounds_mm'), false);
  }
});

test('empty names and same-model duplicates cannot replace saved measurements', () => {
  const storage = memory();
  for (const name of ['', '   ', 'x'.repeat(81)]) assert.throws(() => saveVersion(storage, models, tray, tray.defaults, name), /1 to 80/);
  saveVersion(storage, models, tray, tray.defaults, ' Desk drawer ');
  const original = storage.text;
  assert.throws(() => saveVersion(storage, models, tray, { ...tray.defaults, length: 180.5 }, 'DESK DRAWER'), /already has/);
  assert.equal(storage.text, original);
  const cable = models.find((item: any) => item.name === 'cable_comb');
  assert.equal(saveVersion(storage, models, cable, cable.defaults, 'Desk drawer').length, 2);
});

test('the 20-version limit preserves records and removing one permits another save', () => {
  const storage = memory();
  for (let i = 0; i < MAX_VERSIONS; i++) saveVersion(storage, models, tray, { ...tray.defaults, length: 150 + i }, 'Size ' + i);
  const saved = readVersions(storage, models);
  const original = storage.text;
  assert.throws(() => saveVersion(storage, models, tray, tray.defaults, 'Overflow'), /20 saved versions/);
  assert.equal(storage.text, original);
  removeVersion(storage, models, saved[5].id);
  const next = saveVersion(storage, models, tray, tray.defaults, 'Replacement');
  assert.equal(next.length, MAX_VERSIONS);
  assert.deepEqual(next.slice(1), saved.filter((record: any) => record.id !== saved[5].id));
});

test('malformed, oversized and incompatible stored records are never silently overwritten', () => {
  const valid = memory();
  saveVersion(valid, models, tray, tray.defaults, 'Original');
  const row = JSON.parse(valid.text!)[0];
  const cases = ['broken', '{}', '[]'.repeat(32769), JSON.stringify(Array(21).fill(row))];
  for (const edit of [
    { id: 'wrong' }, { name: '' }, { dimensions: { ...row.dimensions, model: 'missing' } },
    { dimensions: { ...row.dimensions, units: 'inch' } },
    { dimensions: { ...row.dimensions, parameters: { ...tray.defaults, length: '180' } } },
    { dimensions: { ...row.dimensions, parameters: { ...tray.defaults, length: 1001 } } },
    { dimensions: { ...row.dimensions, parameters: { length: 180 } } },
  ]) cases.push(JSON.stringify([{ ...row, ...edit }]));
  cases.push(JSON.stringify([row, row]));
  for (const text of cases) {
    const storage = memory(text);
    assert.throws(() => readVersions(storage, models));
    assert.throws(() => saveVersion(storage, models, tray, tray.defaults, 'New'));
    assert.equal(storage.text, text);
  }
});

test('quota and denied-storage failures leave previously saved versions intact', () => {
  const storage = memory();
  const original = saveVersion(storage, models, tray, tray.defaults, 'Original');
  const text = storage.text;
  storage.setItem = () => { throw new DOMException('Full', 'QuotaExceededError'); };
  assert.throws(() => saveVersion(storage, models, tray, tray.defaults, 'New'), /Full/);
  assert.throws(() => removeVersion(storage, models, original[0].id), /Full/);
  assert.equal(storage.text, text);
  assert.deepEqual(readVersions(storage, models), original);
  storage.getItem = () => { throw new DOMException('Denied', 'SecurityError'); };
  assert.throws(() => readVersions(storage, models), /Denied/);
});

test('actions read current storage and preserve versions saved by another view', () => {
  const storage = memory();
  const oldView = saveVersion(storage, models, tray, tray.defaults, 'First');
  const anotherView = saveVersion(storage, models, tray, { ...tray.defaults, length: 170 }, 'Second');
  const current = saveVersion(storage, models, tray, { ...tray.defaults, length: 180.5 }, 'Third');
  assert.deepEqual(current.slice(1), anotherView);
  const removed = removeVersion(storage, models, oldView[0].id);
  assert.deepEqual(removed.map((record: any) => record.name), ['Third', 'Second']);
  const text = storage.text;
  assert.throws(() => removeVersion(storage, models, oldView[0].id), /no longer saved/);
  assert.equal(storage.text, text);
});

test('portable backups restore every model with fresh identities and canonical kit quantities', () => {
  for (let start = 0; start < models.length; start += MAX_VERSIONS) {
    const source = memory(), destination = memory();
    for (const item of models.slice(start, start + MAX_VERSIONS)) saveVersion(source, models, item, item.defaults, item.title);
    const text = versionBackup(source, models);
    const backup = JSON.parse(text);
    assert.equal(backup.format, 'everyday-prints-versions');
    assert.equal(backup.version, 1);
    assert.ok(backup.versions.every((record: any) => !Object.hasOwn(record, 'id')));
    const result = importVersionBackup(destination, models, text);
    assert.equal(result.added, Math.min(MAX_VERSIONS, models.length - start));
    const old = readVersions(source, models);
    assert.deepEqual(result.records.map(({ name, dimensions }: any) => ({ name, dimensions })), backup.versions);
    assert.ok(result.records.every((record: any) => !old.some((item: any) => item.id === record.id)));
  }
});

test('conflicting names keep both measurements and repeated imports are idempotent', () => {
  const source = memory(), target = memory();
  saveVersion(source, models, tray, { ...tray.defaults, length: 180.5 }, 'Desk drawer');
  const old = saveVersion(target, models, tray, tray.defaults, 'Desk drawer');
  saveVersion(target, models, tray, { ...tray.defaults, length: 170 }, 'Desk drawer (2)');
  const result = importVersionBackup(target, models, versionBackup(source, models));
  assert.equal(result.records[0].name, 'Desk drawer (3)');
  assert.equal(result.records[0].dimensions.parameters.length, 180.5);
  assert.ok(result.records.some((row: any) => row.id === old[0].id && row.dimensions.parameters.length === 150));
  const text = target.text;
  target.setItem = () => { throw new Error('A repeated import should not write'); };
  const repeated = importVersionBackup(target, models, versionBackup(source, models));
  assert.equal(repeated.added, 0);
  assert.equal(repeated.skipped, 1);
  assert.equal(target.text, text);
  const longName = '🙂'.repeat(40);
  const longSource = memory(), longTarget = memory();
  saveVersion(longSource, models, tray, { ...tray.defaults, length: 180.5 }, longName);
  saveVersion(longTarget, models, tray, tray.defaults, longName);
  const renamed = importVersionBackup(longTarget, models, versionBackup(longSource, models)).records[0].name;
  assert.ok(renamed.length <= 80 && renamed.endsWith(' (2)'));
  assert.equal(renamed, '🙂'.repeat(38) + ' (2)');
});

test('real decimal and ordered list versions keep exact values while backup geometry metadata is discarded', () => {
  const source = memory(), target = memory();
  for (const name of ['parts_tray', 'cable_comb']) {
    const item = models.find((item: any) => item.name === name);
    const exported = JSON.parse(readFileSync(resolve(cloud, '../review/cloud_export_samples', name, 'parameters.json'), 'utf8'));
    saveVersion(source, models, item, exported.parameters, 'Kitchen <wide> ✓');
  }
  const backup = JSON.parse(versionBackup(source, models));
  for (const row of backup.versions) { row.id = 'untrusted'; row.dimensions.bounds_mm = [999, 999, 999]; row.dimensions.mesh_sha256 = 'fake'; }
  const result = importVersionBackup(target, models, JSON.stringify(backup));
  assert.deepEqual(result.records.map((row: any) => row.dimensions), readVersions(source, models).map((row: any) => row.dimensions));
});

test('invalid mixed backups and unknown schemas cannot partly replace the library', () => {
  const source = memory(), target = memory();
  saveVersion(source, models, tray, { ...tray.defaults, length: 180.5 }, 'New');
  saveVersion(target, models, tray, tray.defaults, 'Original');
  const valid = JSON.parse(versionBackup(source, models));
  const wrong = { ...valid.versions[0], dimensions: { ...valid.versions[0].dimensions, parameters: { ...tray.defaults, length: '180' } } };
  const cases = ['broken', '{}', JSON.stringify({ ...valid, version: 2 }), JSON.stringify({ ...valid, versions: [] }),
    JSON.stringify({ ...valid, versions: [...valid.versions, wrong] }), JSON.stringify({ ...valid, versions: Array(21).fill(valid.versions[0]) })];
  const original = target.text;
  for (const text of cases) {
    assert.throws(() => importVersionBackup(target, models, text));
    assert.equal(target.text, original);
  }
  assert.throws(() => versionBackup(memory(), models), /Save a named version/);
});

test('backup byte limits count UTF-8 and accept an exact-boundary BOM file', () => {
  const source = memory();
  saveVersion(source, models, tray, tray.defaults, 'Étagère ✓');
  const text = '\uFEFF' + versionBackup(source, models);
  const boundary = text + ' '.repeat(MAX_VERSIONS_BYTES - new TextEncoder().encode(text).byteLength);
  assert.equal(new TextEncoder().encode(boundary).byteLength, MAX_VERSIONS_BYTES);
  assert.equal(importVersionBackup(memory(), models, boundary).added, 1);
  const target = memory();
  assert.throws(() => importVersionBackup(target, models, boundary + 'é'), /exceeds 64 KiB/);
  assert.equal(target.text, null);
});

test('capacity, failed writes and newer records are respected when merging a backup', () => {
  const source = memory(), target = memory();
  saveVersion(source, models, tray, { ...tray.defaults, length: 180.5 }, 'Incoming');
  for (let i = 0; i < MAX_VERSIONS; i++) saveVersion(target, models, tray, tray.defaults, 'Existing ' + i);
  const text = versionBackup(source, models), full = target.text;
  assert.throws(() => importVersionBackup(target, models, text), /exceed 20/);
  assert.equal(target.text, full);
  const fresh = memory();
  saveVersion(fresh, models, tray, tray.defaults, 'Saved by another view');
  const original = fresh.text;
  const setItem = fresh.setItem;
  fresh.setItem = () => { throw new DOMException('Full', 'QuotaExceededError'); };
  assert.throws(() => importVersionBackup(fresh, models, text), /Full/);
  assert.equal(fresh.text, original);
  fresh.setItem = setItem;
  const imported = importVersionBackup(fresh, models, text);
  assert.equal(imported.records[1].name, 'Saved by another view');
  assert.equal(imported.records[0].name, 'Incoming');
});
