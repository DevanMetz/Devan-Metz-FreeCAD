import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { verifyMesh } from '../web/mesh.js';

const cloud = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const arrayBuffer = (data: Buffer) => data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);

function triangle() {
  const buffer = new ArrayBuffer(134);
  const view = new DataView(buffer);
  view.setUint32(80, 1, true);
  const values = [0, 0, 1, -1, -2, -3, 1, -2, -3, -1, 1, 1];
  values.forEach((value, index) => view.setFloat32(84 + index * 4, value, true));
  return buffer;
}

test('all 53 catalog meshes agree with their reported CAD dimensions', () => {
  const catalog = JSON.parse(readFileSync(resolve(cloud, 'public/catalog.json'), 'utf8'));
  assert.equal(catalog.models.length, 53);
  for (const model of catalog.models) {
    const data = readFileSync(resolve(cloud, 'public', model.mesh.slice(1)));
    assert.doesNotThrow(() => verifyMesh(arrayBuffer(data), model.bounds_mm), model.name);
  }
});

test('real custom downloads and kit components retain their mesh dimensions', () => {
  const samples = resolve(cloud, '../review/cloud_export_samples');
  let checked = 0;
  for (const path of readdirSync(samples, { recursive: true })) {
    if (!String(path).endsWith('parameters.json')) continue;
    const file = resolve(samples, String(path));
    const metadata = JSON.parse(readFileSync(file, 'utf8'));
    if (!metadata.printable) continue;
    const data = readFileSync(resolve(dirname(file), metadata.model + '.stl'));
    assert.doesNotThrow(() => verifyMesh(arrayBuffer(data), metadata.bounds_mm), String(path));
    checked++;
  }
  assert.ok(checked >= 4, 'Expected existing real CAD fixtures');
});

test('negative coordinates, a solid header, attributes and small tessellation differences remain valid', () => {
  const buffer = triangle();
  new Uint8Array(buffer).set(new TextEncoder().encode('solid binary mesh'));
  new DataView(buffer).setUint16(132, 65535, true);
  assert.deepEqual(verifyMesh(buffer, [2.04, 3, 4]), [2, 3, 4]);
});

test('empty, truncated, trailing and mismatched facet records cannot become a verified mesh', () => {
  const wrongCount = triangle();
  new DataView(wrongCount).setUint32(80, 4294967295, true);
  for (const buffer of [new ArrayBuffer(0), new ArrayBuffer(83), new ArrayBuffer(84), triangle().slice(0, 133), new ArrayBuffer(135), wrongCount]) {
    assert.throws(() => verifyMesh(buffer, [2, 3, 4]), /mesh file could not be verified/);
  }
});

test('nonfinite normals and vertex coordinates cannot become a verified mesh', () => {
  for (let component = 0; component < 12; component++) {
    for (const value of [NaN, Infinity, -Infinity]) {
      const buffer = triangle();
      new DataView(buffer).setFloat32(84 + component * 4, value, true);
      assert.throws(() => verifyMesh(buffer, [2, 3, 4]), /mesh file could not be verified/);
    }
  }
});

test('collapsed geometry and dimensions outside tessellation tolerance are rejected', () => {
  const flat = triangle();
  const view = new DataView(flat);
  for (const offset of [104, 116, 128]) view.setFloat32(offset, 0, true);
  assert.throws(() => verifyMesh(flat, [2, 3, 4]), /mesh file could not be verified/);
  for (let axis = 0; axis < 3; axis++) {
    const bounds = [2, 3, 4];
    bounds[axis] += .06;
    assert.throws(() => verifyMesh(triangle(), bounds), /mesh dimensions do not match/);
  }
});
