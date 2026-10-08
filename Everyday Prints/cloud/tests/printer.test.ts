import assert from 'node:assert/strict';
import test from 'node:test';
import { PRINTER_STORAGE, readPrinterVolume, validPrinterVolume } from '../web/printer.js';

function storage(raw: string | null) {
  return { getItem(key: string) { assert.equal(key, PRINTER_STORAGE); return raw; } };
}

test('missing settings clear the profile and exact positive decimal volumes read independently', () => {
  assert.equal(readPrinterVolume(storage(null)), null);
  const saved = storage('[180.55555555555554,100,24.00001]');
  const volume = readPrinterVolume(saved);
  assert.deepEqual(volume, [180.55555555555554, 100, 24.00001]);
  volume![0] = 1;
  assert.equal(readPrinterVolume(saved)![0], 180.55555555555554);
});

test('profile validation rejects wrong shapes, coercion, nonfinite numbers and nonpositive axes', () => {
  for (const value of [null, {}, 100, [], [1, 2], [1, 2, 3, 4], ['1', 2, 3], [true, 2, 3], [1, [2], 3], [0, 2, 3], [-1, 2, 3], [NaN, 2, 3], [Infinity, 2, 3]]) {
    assert.equal(validPrinterVolume(value), false, JSON.stringify(value));
  }
  assert.equal(validPrinterVolume([1e-7, 1e308, 2.5]), true);
  for (const raw of ['null', '{}', '100', '[]', '[1,2]', '[1,2,3,4]', '["1",2,3]', '[true,2,3]', '[1,[2],3]', '[0,2,3]', '[-1,2,3]', '[1e309,2,3]']) {
    assert.throws(() => readPrinterVolume(storage(raw)), /could not be read/);
  }
});

test('the 256-character limit accepts the exact boundary and rejects longer records', () => {
  const body = '[150,100,24]';
  assert.deepEqual(readPrinterVolume(storage(body + ' '.repeat(256 - body.length))), [150, 100, 24]);
  assert.throws(() => readPrinterVolume(storage(body + ' '.repeat(257 - body.length))), /could not be read/);
});

test('corrupt and denied reads preserve stored data without a write', () => {
  let raw = '{bad json', writes = 0;
  const saved = { getItem() { return raw; }, setItem() { ++writes; }, removeItem() { ++writes; } };
  assert.throws(() => readPrinterVolume(saved), /could not be read/);
  assert.equal(raw, '{bad json');
  assert.equal(writes, 0);
  const denied = Object.assign(new Error('Denied'), { name: 'SecurityError' });
  assert.throws(() => readPrinterVolume({ getItem() { throw denied; } }), error => error === denied);
});

test('every read uses the newest stored settings instead of a captured event value', () => {
  let raw: string | null = '[150,100,24]';
  const saved = { getItem() { return raw; } };
  assert.deepEqual(readPrinterVolume(saved), [150, 100, 24]);
  raw = '[100,180.55555555555554,25]';
  assert.deepEqual(readPrinterVolume(saved), [100, 180.55555555555554, 25]);
  raw = null;
  assert.equal(readPrinterVolume(saved), null);
});
