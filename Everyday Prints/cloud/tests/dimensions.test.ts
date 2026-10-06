import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { MAX_DIMENSIONS_BYTES, dimensionParameters, dimensionRecord, savedDimensions } from '../web/dimensions.js';

const models = JSON.parse(readFileSync(new URL('../public/catalog.json', import.meta.url), 'utf8')).models;
const model = name => models.find(item => item.name === name);
const load = record => savedDimensions(JSON.stringify(record), models);
const record = (parameters = {}, name = 'parts_tray') => ({ model: name, units: 'mm', parameters });

test('all 53 model defaults round-trip through saved dimensions', () => {
  assert.equal(models.length, 53);
  for (const item of models) {
    const saved = dimensionRecord(item, item.defaults);
    const loaded = load(saved);
    assert.equal(loaded.item.name, item.name);
    assert.deepEqual(loaded.parameters, item.defaults);
  }
});

test('partial files restore defaults without sharing mutable numeric lists', () => {
  const item = model('cable_comb');
  const loaded = load(record({ depth: 40 }, item.name));
  assert.equal(loaded.parameters.depth, 40);
  assert.deepEqual(loaded.parameters.cable_diameters, item.defaults.cable_diameters);
  loaded.parameters.cable_diameters[0] = 99;
  assert.notEqual(item.defaults.cable_diameters[0], 99);
});

test('continuous decimals are accepted and counts remain whole', () => {
  assert.equal(load(record({ length: 180.55 })).parameters.length, 180.55);
  assert.throws(() => load(record({ columns: 2.5 })), /whole number/);
});

test('numeric lists retain order and reject wrong shapes or too many entries', () => {
  const item = model('cable_comb');
  const values = [9, 2, 3.5];
  const saved = dimensionRecord(item, { cable_diameters: values });
  assert.deepEqual(saved.parameters.cable_diameters, values);
  values[0] = 5;
  assert.equal(saved.parameters.cable_diameters[0], 9);
  for (const bad of [[], Array(17).fill(3), '2, 3', { diameter: 2 }]) {
    assert.throws(() => load(record({ cable_diameters: bad }, item.name)), /1 to 16 numbers/);
  }
  assert.throws(() => load(record({ length: [180] })), /one number/);
});

test('malformed files, unknown models, missing parameters and wrong units fail clearly', () => {
  assert.throws(() => savedDimensions('{', models), /not valid JSON/);
  for (const value of [null, [], 3]) assert.throws(() => load(value), /Choose a saved dimensions/);
  for (const units of ['inch', undefined, null]) assert.throws(() => load({ ...record(), units }), /millimeters/);
  assert.throws(() => load(record({}, 'no_such_model')), /not in the library/);
  for (const parameters of [undefined, null, [], 2]) assert.throws(() => load({ ...record(), parameters }), /parameters object/);
});

test('unknown keys and invalid numeric values cannot reach the editor', () => {
  assert.throws(() => savedDimensions('{"model":"parts_tray","units":"mm","parameters":{"__proto__":1}}', models), /Unknown parameter/);
  for (const value of ['180', null, true, 1001, -1001]) assert.throws(() => load(record({ length: value })), /numbers between/);
  assert.throws(() => savedDimensions('{"model":"parts_tray","units":"mm","parameters":{"length":1e309}}', models), /numbers between/);
});

test('every catalog field enforces its supported range across parameters and saved files', () => {
  for (const item of models) for (const field of item.parameters) {
    if (field.type === 'list') continue;
    for (const bound of ['min', 'max']) {
      if (field[bound] === undefined) continue;
      const limit = field[bound];
      assert.equal(dimensionParameters(item, { [field.key]: limit })[field.key], limit);
      const value = limit + (bound === 'min' ? -1 : 1) * (field.type === 'integer' ? 1 : 0.001);
      assert.throws(() => dimensionParameters(item, { [field.key]: value }), /use a number/);
      assert.throws(() => load(record({ [field.key]: value }, item.name)), /use a number/);
    }
  }
});

test('unbounded fields and numeric lists retain the service magnitude cap', () => {
  const tray = model('parts_tray');
  for (const value of [-1000, 1000]) assert.equal(dimensionParameters(tray, { outer_radius: value }).outer_radius, value);
  for (const value of [-1000.001, 1000.001, Infinity, NaN]) assert.throws(() => dimensionParameters(tray, { outer_radius: value }), /numbers between/);
  const comb = model('cable_comb');
  assert.deepEqual(dimensionParameters(comb, { cable_diameters: [-1000, 3.55, 1000] }).cable_diameters, [-1000, 3.55, 1000]);
  for (const value of [1001, -1001, null, '3', true, Infinity, NaN]) assert.throws(() => dimensionParameters(comb, { cable_diameters: [3, value] }), /numbers between/);
});

test('shared parameter validation does not coerce values or partly apply invalid records', () => {
  const item = model('parts_tray');
  const before = structuredClone(item.defaults);
  for (const overrides of [null, [], 0, '180']) assert.throws(() => dimensionParameters(item, overrides), /parameters object/);
  for (const value of ['180', null, true]) assert.throws(() => dimensionParameters(item, { length: value }), /numbers between/);
  assert.throws(() => dimensionParameters(item, { length: 180.55, width: 251 }), /Width: use a number between 30 and 250/);
  assert.throws(() => dimensionParameters(item, { unexpected: 1 }), /Unknown parameter/);
  assert.deepEqual(item.defaults, before);
});

test('numeric validation identifies the field while file-level failures stay unassigned', () => {
  for (const [name, key, value] of [
    ['parts_tray', 'length', [180]], ['parts_tray', 'length', 251],
    ['parts_tray', 'columns', 2.5], ['parts_tray', 'outer_radius', 1001],
    ['cable_comb', 'cable_diameters', []], ['cable_comb', 'cable_diameters', [3, '4']],
  ]) {
    assert.throws(() => dimensionParameters(model(name), { [key]: value }), error => {
      assert.ok(error instanceof Error);
      assert.equal(error.parameter, key);
      assert.ok(error.message.startsWith(model(name).parameters.find(field => field.key === key).label));
      return true;
    });
  }
  for (const overrides of [null, { unexpected: 1 }]) {
    assert.throws(() => dimensionParameters(model('parts_tray'), overrides), error => !Object.hasOwn(error, 'parameter'));
  }
});

test('the 16 KiB cap counts UTF-8 bytes and Windows UTF-8 BOM files load', () => {
  const text = JSON.stringify(record({ length: 180.55 }));
  const exact = text + ' '.repeat(MAX_DIMENSIONS_BYTES - new TextEncoder().encode(text).byteLength);
  assert.equal(savedDimensions(exact, models).parameters.length, 180.55);
  assert.throws(() => savedDimensions(exact + ' ', models), /exceeds 16 KiB/);
  const multibyte = JSON.stringify({ ...record(), note: 'é'.repeat(MAX_DIMENSIONS_BYTES / 2) });
  assert.ok(multibyte.length < MAX_DIMENSIONS_BYTES);
  assert.throws(() => savedDimensions(multibyte, models), /exceeds 16 KiB/);
  assert.equal(savedDimensions('\uFEFF' + text, models).parameters.length, 180.55);
});

test('saved assembly inventories come from the catalog and file geometry metadata is ignored', () => {
  const item = model('strap_clamp_assembly');
  const loaded = load({ ...record({}, item.name), kit: [{ model: 'wrong', quantity: 999 }], mesh_sha256: 'untrusted', printable: true, bounds_mm: [1, 1, 1] });
  const saved = dimensionRecord(loaded.item, loaded.parameters);
  assert.deepEqual(saved.kit, item.kit);
  assert.equal(saved.kit[0].quantity, 4);
  assert.ok(!Object.hasOwn(saved, 'mesh_sha256'));
  assert.ok(!Object.hasOwn(saved, 'bounds_mm'));
  saved.kit[0].quantity = 1;
  assert.equal(item.kit[0].quantity, 4);
});
