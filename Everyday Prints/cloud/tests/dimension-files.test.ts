import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';
import { ZipWriter, Uint8ArrayWriter, Uint8ArrayReader } from '@zip.js/zip.js/lib/zip-core-custom.js';
import { checkDimensionsFile, MAX_DIMENSIONS_ZIP_BYTES, readDimensionsFile } from '../web/dimension-files.js';
import { MAX_DIMENSIONS_BYTES, savedDimensions } from '../web/dimensions.js';

const models = JSON.parse(readFileSync(new URL('../public/catalog.json', import.meta.url), 'utf8')).models;
const sampleRoot = new URL('../../review/cloud_export_samples/', import.meta.url);
const record = JSON.stringify({ model: 'parts_tray', units: 'mm', parameters: { length: 180.55 } });
const file = (bytes, name = 'dimensions.zip', type = 'application/zip') => new File([bytes], name, { type });
const encode = text => new TextEncoder().encode(text);

async function archive(entries, level = 6) {
  const writer = new ZipWriter(new Uint8ArrayWriter(), { useWebWorkers: false });
  for (const [name, data] of entries) await writer.add(name, new Uint8ArrayReader(typeof data === 'string' ? encode(data) : data), { level, dataDescriptor: false });
  return writer.close();
}

function replaceBytes(bytes, before, after, firstOnly = false) {
  const result = Uint8Array.from(bytes), find = encode(before), replacement = encode(after);
  assert.equal(find.length, replacement.length);
  let count = 0;
  for (let i = 0; i <= result.length - find.length; i++) {
    if (find.every((value, index) => result[i + index] === value)) {
      result.set(replacement, i);
      count++;
      if (firstOnly) break;
      i += find.length - 1;
    }
  }
  assert.ok(count);
  return result;
}

test('all real CAD and kit ZIP fixtures load their exact canonical dimensions', async () => {
  const names = readdirSync(sampleRoot, { withFileTypes: true }).filter(entry => entry.isDirectory()).map(entry => entry.name);
  assert.ok(names.length >= 10);
  for (const name of names) {
    const text = await readDimensionsFile(file(readFileSync(new URL(name + '/download.zip', sampleRoot))));
    const record = JSON.parse(text), loaded = savedDimensions(text, models);
    assert.equal(loaded.item.name, record.model);
    assert.deepEqual(loaded.parameters, record.parameters);
  }
});

test('stored and deflated ZIPs preserve UTF-8, BOMs and the exact record byte boundary', async () => {
  const text = '\uFEFF' + record + ' '.repeat(MAX_DIMENSIONS_BYTES - encode('\uFEFF' + record).byteLength);
  for (const level of [0, 6]) {
    const bytes = await archive([['parameters.json', text], ['notes.txt', 'å\u{1F9F0}']], level);
    assert.equal(await readDimensionsFile(file(bytes, 'TRAY.ZIP', '')), text.replace(/^\uFEFF/, ''));
    assert.equal(savedDimensions(await readDimensionsFile(file(bytes)), models).parameters.length, 180.55);
  }
  const json = file(encode(record), 'parameters.json', 'application/json');
  assert.equal(await readDimensionsFile(json), record);
  assert.equal(await readDimensionsFile(file(await archive([['parameters.json', record]]), 'cad', 'application/x-zip-compressed')), record);
});

test('ZIP and JSON byte caps reject files before reading their contents', async () => {
  for (const [name, type, size, pattern] of [
    ['cad.zip', '', MAX_DIMENSIONS_ZIP_BYTES + 1, /exceeds 8 MiB/],
    ['cad', 'application/zip', MAX_DIMENSIONS_ZIP_BYTES + 1, /exceeds 8 MiB/],
    ['dimensions.json', 'application/json', MAX_DIMENSIONS_BYTES + 1, /exceeds 16 KiB/],
  ]) {
    let reads = 0;
    const oversized = { name, type, size, text: () => { reads++; return record; } };
    assert.throws(() => checkDimensionsFile(oversized), pattern);
    await assert.rejects(readDimensionsFile(oversized), pattern);
    assert.equal(reads, 0);
  }
  assert.doesNotThrow(() => checkDimensionsFile({ name: 'cad.zip', type: '', size: MAX_DIMENSIONS_ZIP_BYTES }));
});

test('missing, nested, duplicate and contradictory ZIP records never load dimensions', async () => {
  await assert.rejects(readDimensionsFile(file(await archive([['other.json', record]]))), /no parameters.json/);
  await assert.rejects(readDimensionsFile(file(await archive([['nested/parameters.json', record]]))), /no parameters.json/);
  const two = await archive([['parameters.json', record], ['dimensions.json', record]]);
  await assert.rejects(readDimensionsFile(file(replaceBytes(two, 'dimensions.json', 'parameters.json'))), /one parameters.json/);
  const normal = await archive([['parameters.json', record]]);
  await assert.rejects(readDimensionsFile(file(replaceBytes(normal, 'parameters.json', 'dimensions.json', true))), /could not be verified/);
  await assert.rejects(readDimensionsFile(file(normal.slice(0, -5))), /could not be verified/);
});

test('CRC corruption and invalid UTF-8 are rejected even when the JSON shape looks valid', async () => {
  const bytes = await archive([['parameters.json', record]], 0);
  await assert.rejects(readDimensionsFile(file(replaceBytes(bytes, '180.55', '190.55', true))), /could not be verified/);
  await assert.rejects(readDimensionsFile(file(await archive([['parameters.json', new Uint8Array([0xff, 0xfe, 0x7b])]]))), /could not be verified/);
});

test('encrypted records and unsupported ZIP compression have an extraction fallback', async () => {
  const original = await archive([['parameters.json', record]]);
  for (const encrypted of [true, false]) {
    const bytes = Uint8Array.from(original), view = new DataView(bytes.buffer);
    for (let i = 0; i < bytes.length - 46; i++) {
      const signature = view.getUint32(i, true);
      if (signature !== 0x04034b50 && signature !== 0x02014b50) continue;
      const offset = i + (signature === 0x04034b50 ? 6 : 8);
      if (encrypted) view.setUint16(offset, view.getUint16(offset, true) | 1, true);
      else view.setUint16(offset + 2, 99, true);
    }
    await assert.rejects(readDimensionsFile(file(bytes)), encrypted ? /unencrypted CAD or kit ZIP/ : /compression is unsupported/);
  }
});

test('entry count, archive expansion and dimensions expansion are bounded before use', async () => {
  const many = [['parameters.json', record], ...Array.from({ length: 128 }, (_, i) => ['extra' + i, 'x'])];
  await assert.rejects(readDimensionsFile(file(await archive(many))), /too many files/);
  const expanded = await archive([['parameters.json', record], ['large.bin', new Uint8Array(24 * 1024 * 1024)]]);
  await assert.rejects(readDimensionsFile(file(expanded)), /contents exceed 24 MiB/);
  const bigRecord = await archive([['parameters.json', record + ' '.repeat(MAX_DIMENSIONS_BYTES)]]);
  await assert.rejects(readDimensionsFile(file(bigRecord)), /record exceeds 16 KiB/);
});

test('falsely small ZIP size fields cannot bypass the actual output limit', async () => {
  const original = await archive([['parameters.json', record + ' '.repeat(1024 * 1024)]]);
  const bytes = Uint8Array.from(original), view = new DataView(bytes.buffer);
  for (let i = 0; i < bytes.length - 46; i++) {
    const signature = view.getUint32(i, true);
    if (signature === 0x04034b50) view.setUint32(i + 22, record.length, true);
    else if (signature === 0x02014b50) view.setUint32(i + 24, record.length, true);
  }
  await assert.rejects(readDimensionsFile(file(bytes)), /record exceeds 16 KiB|could not be verified/);
});

test('cancelled ZIP reads and missing browser decompression leave JSON imports available', async () => {
  const bytes = await archive([['parameters.json', record]]);
  const controller = new AbortController(), reason = new Error('Controlled cancellation');
  controller.abort(reason);
  await assert.rejects(readDimensionsFile(file(bytes), controller.signal), error => error === reason);
  const real = globalThis.DecompressionStream;
  try {
    globalThis.DecompressionStream = undefined;
    await assert.rejects(readDimensionsFile(file(bytes)), /unavailable in this browser/);
    assert.equal(await readDimensionsFile(file(encode(record), 'parameters.json', 'application/json')), record);
  } finally { globalThis.DecompressionStream = real; }
});
