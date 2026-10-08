import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { MAX_VERSIONS, VERSIONS_KEY, readVersions, removeVersion, saveVersion } from '../web/versions.js';

const cloud = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const models = JSON.parse(readFileSync(resolve(cloud, 'public/catalog.json'), 'utf8')).models;
const tray = models.find((item: any) => item.name === 'parts_tray');
function memory(text: string | null = null) {
  return { text, getItem(key: string) { assert.equal(key, VERSIONS_KEY); return this.text; },
    setItem(key: string, value: string) { assert.equal(key, VERSIONS_KEY); this.text = value; } };
}

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
