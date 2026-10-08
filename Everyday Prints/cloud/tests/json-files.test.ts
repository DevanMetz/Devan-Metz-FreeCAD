import assert from 'node:assert/strict';
import { getEventListeners } from 'node:events';
import test from 'node:test';
import { readJsonFile } from '../web/json-files.js';

const encode = text => new TextEncoder().encode(text);
const file = bytes => new File([bytes], 'saved.json', { type: 'application/json' });

test('JSON bytes preserve Unicode, literal replacement characters, BOMs and exact input boundaries', async () => {
  const record = JSON.stringify({ name: 'Étagère <wide> 🧰 �', parameters: { length: 180.55, sizes: [9, 2.5, 4] } });
  for (const limit of [16384, 65536]) {
    const body = encode('\uFEFF' + record + ' '.repeat(limit - encode('\uFEFF' + record).byteLength));
    assert.equal(body.byteLength, limit);
    const signal = new AbortController().signal;
    assert.equal(await readJsonFile(file(body), signal, limit), record + ' '.repeat(limit - encode('\uFEFF' + record).byteLength));
    assert.equal(getEventListeners(signal, 'abort').length, 0);
    assert.deepEqual(JSON.parse(await readJsonFile(file(body), undefined, limit)), JSON.parse(record));
  }
});

test('invalid UTF-8 never becomes repaired JSON, including malformed bytes inside otherwise valid strings', async () => {
  const before = encode('{"name":"Broken '), after = encode('","parameters":{"length":180.55}}');
  const invalid = [[0xff], [0x80], [0xc0, 0xaf], [0xe0, 0x80, 0x80], [0xed, 0xa0, 0x80],
    [0xf4, 0x90, 0x80, 0x80], [0xf0, 0x9f], [0xff, 0xfe]];
  for (const middle of invalid) {
    const bytes = new Uint8Array([...before, ...middle, ...after]);
    assert.doesNotThrow(() => JSON.parse(new TextDecoder().decode(bytes)));
    await assert.rejects(readJsonFile(file(bytes), new AbortController().signal, 65536),
      error => error.jsonFile === true && /not valid UTF-8/.test(error.message));
  }
});

test('declared and actual JSON byte caps reject before decoding or applying a record', async () => {
  for (const limit of [16384, 65536]) {
    let reads = 0;
    const source = { size: limit + 1, arrayBuffer: async () => { reads++; return encode('{}').buffer; } };
    await assert.rejects(readJsonFile(source, undefined, limit), /exceeds/);
    assert.equal(reads, 0);
    source.size = 1;
    source.arrayBuffer = async () => { reads++; return new Uint8Array(limit + 1).buffer; };
    await assert.rejects(readJsonFile(source, undefined, limit), error => error.jsonFile === true && /exceeds/.test(error.message));
    assert.equal(reads, 1);
  }
});

test('aborted JSON waits release listeners and ignore late malformed bytes or read failures', { timeout: 2000 }, async () => {
  for (const fail of [false, true]) {
    let resolve, reject, reads = 0;
    const source = { size: 1, arrayBuffer: () => { reads++; return new Promise((done, failed) => { resolve = done; reject = failed; }); } };
    const controller = new AbortController(), reason = new Error('Newer file');
    const pending = readJsonFile(source, controller.signal, 16384);
    controller.abort(reason);
    await assert.rejects(pending, error => error === reason);
    assert.equal(getEventListeners(controller.signal, 'abort').length, 0);
    if (fail) reject(new Error('Late read failure'));
    else resolve(new Uint8Array([0xff]).buffer);
    await new Promise(done => setImmediate(done));
    await assert.rejects(readJsonFile(source, controller.signal, 16384), error => error === reason);
    assert.equal(reads, 1);
    assert.equal(await readJsonFile(file(encode('{}')), undefined, 16384), '{}');
  }
});
