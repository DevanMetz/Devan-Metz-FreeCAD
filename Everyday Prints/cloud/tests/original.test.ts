import assert from 'node:assert/strict';
import test from 'node:test';
import { ORIGINAL_IDLE_MS, readOriginal } from '../web/original.js';
import { MAX_FILE_BYTES } from '../web/transfer.js';

const url = 'https://everyday-prints.test/models/parts_tray.stl';
async function flush() { for (let n = 0; n < 12; ++n) await Promise.resolve(); }
function body() {
  let release;
  const stats = { cancelled: 0, released: 0, reads: 0 };
  const response = { ok: true, headers: new Headers({ 'Content-Type': 'model/stl' }), body: {
    getReader: () => ({
      read: () => { ++stats.reads; return new Promise(resolve => { release = resolve; }); },
      cancel: () => { ++stats.cancelled; return new Promise(() => {}); },
      releaseLock: () => { ++stats.released; },
    })
  } };
  return { response, stats, send: chunk => release(chunk) };
}

test('original and reload requests return exact bytes and remove their abort listener after completion', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const bytes = new Uint8Array([0, 1, 2, 255]);
  for (const reload of [false, true]) {
    const parent = new AbortController();
    let child;
    context.mock.method(globalThis, 'fetch', async (input, options) => {
      assert.equal(input, url);
      assert.equal(options.cache, reload ? 'reload' : undefined);
      child = options.signal;
      return new Response(bytes);
    });
    const progress = [];
    assert.deepEqual(new Uint8Array(await readOriginal(url, parent.signal, n => progress.push(n), reload)), bytes);
    assert.deepEqual(progress, [0, 4]);
    parent.abort();
    context.mock.timers.tick(ORIGINAL_IDLE_MS * 2);
    assert.equal(child.aborted, false);
  }
});

test('an already stopped request never fetches and synchronous failures remove the idle timer', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const parent = new AbortController();
  parent.abort();
  const fetch = context.mock.method(globalThis, 'fetch', () => { throw new Error('Disconnected'); });
  await assert.rejects(readOriginal(url, parent.signal), { name: 'AbortError' });
  assert.equal(fetch.mock.callCount(), 0);
  const current = new AbortController();
  await assert.rejects(readOriginal(url, current.signal), /Disconnected/);
  context.mock.timers.tick(ORIGINAL_IDLE_MS * 2);
  assert.equal(current.signal.aborted, false);
});

test('stalled headers expire at the exact boundary and late responses cancel without being read', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  let release, child, cancelled = 0, reads = 0, settled = false;
  context.mock.method(globalThis, 'fetch', (input, options) => {
    child = options.signal;
    return new Promise(resolve => { release = resolve; });
  });
  const parent = new AbortController();
  const reading = readOriginal(url, parent.signal).finally(() => { settled = true; });
  const failure = assert.rejects(reading, /original preview stopped responding/);
  context.mock.timers.tick(ORIGINAL_IDLE_MS - 1);
  await flush();
  assert.equal(settled, false);
  context.mock.timers.tick(1);
  await failure;
  assert.equal(child.aborted, true);
  assert.equal(parent.signal.aborted, false);
  release({ bodyUsed: false, body: { cancel: async () => { ++cancelled; }, getReader: () => { ++reads; } } });
  await flush();
  assert.equal(cancelled, 1);
  assert.equal(reads, 0);
});

test('stalled bodies release uncooperative readers and ignore late data and progress', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const held = body(), parent = new AbortController(), progress = [];
  context.mock.method(globalThis, 'fetch', async () => held.response);
  const reading = readOriginal(url, parent.signal, n => progress.push(n));
  const failure = assert.rejects(reading, /original preview stopped responding/);
  await flush();
  assert.equal(held.stats.reads, 1);
  context.mock.timers.tick(ORIGINAL_IDLE_MS);
  await failure;
  assert.deepEqual(held.stats, { cancelled: 1, released: 1, reads: 1 });
  assert.equal(parent.signal.aborted, false);
  held.send({ done: false, value: new Uint8Array([1, 2]) });
  await flush();
  assert.deepEqual(progress, [0]);
  assert.equal(held.stats.released, 1);
});

test('headers and positive file bytes reset inactivity so a slow progressing transfer can finish', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const held = body(), parent = new AbortController(), progress = [];
  let release;
  context.mock.method(globalThis, 'fetch', () => new Promise(resolve => { release = resolve; }));
  const reading = readOriginal(url, parent.signal, n => progress.push(n));
  context.mock.timers.tick(ORIGINAL_IDLE_MS - 1);
  release(held.response);
  await flush();
  for (const value of [1, 2, 255]) {
    context.mock.timers.tick(ORIGINAL_IDLE_MS - 1);
    held.send({ done: false, value: new Uint8Array([value]) });
    await flush();
  }
  context.mock.timers.tick(ORIGINAL_IDLE_MS - 1);
  held.send({ done: true });
  assert.deepEqual(new Uint8Array(await reading), new Uint8Array([1, 2, 255]));
  assert.deepEqual(progress, [0, 1, 2, 3]);
  assert.equal(held.stats.cancelled, 0);
  assert.equal(held.stats.released, 1);
});

test('empty chunks cannot keep a stalled transfer alive', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const held = body();
  context.mock.method(globalThis, 'fetch', async () => held.response);
  const reading = readOriginal(url, new AbortController().signal);
  const failure = assert.rejects(reading, /original preview stopped responding/);
  await flush();
  context.mock.timers.tick(ORIGINAL_IDLE_MS - 1);
  held.send({ done: false, value: new Uint8Array(0) });
  await flush();
  context.mock.timers.tick(1);
  await failure;
  assert.equal(held.stats.cancelled, 1);
  assert.equal(held.stats.released, 1);
});

test('parent cancellation supersedes both headers and body waits with the original abort reason', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  for (const mode of ['headers', 'body']) {
    const parent = new AbortController(), held = body();
    let child;
    context.mock.method(globalThis, 'fetch', (input, options) => {
      child = options.signal;
      return mode === 'headers' ? new Promise(() => {}) : Promise.resolve(held.response);
    });
    const reading = readOriginal(url, parent.signal);
    const failure = assert.rejects(reading, error => error === parent.signal.reason);
    await flush();
    parent.abort(new DOMException('Superseded', 'AbortError'));
    await failure;
    context.mock.timers.tick(ORIGINAL_IDLE_MS * 2);
    assert.equal(child.reason, parent.signal.reason);
    assert.equal(held.stats.cancelled, mode === 'body' ? 1 : 0);
  }
});

test('cancellation just after headers resolve discards the body before locking a reader', async context => {
  const parent = new AbortController();
  let cancelled = 0, reads = 0;
  context.mock.method(globalThis, 'fetch', async () => ({ ok: true,
    headers: new Headers({ 'Content-Type': 'model/stl' }), bodyUsed: false,
    body: { cancel: async () => { ++cancelled; }, getReader: () => { ++reads; assert.fail('Expired response read'); } }
  }));
  const reading = readOriginal(url, parent.signal);
  const failure = assert.rejects(reading, error => error === parent.signal.reason);
  await Promise.resolve();
  parent.abort();
  await failure;
  assert.equal(cancelled, 1);
  assert.equal(reads, 0);
});

test('failed or HTML responses cancel unread bodies and existing byte limits stay enforced', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  let current;
  context.mock.method(globalThis, 'fetch', async () => current);
  for (const details of [{ ok: false, type: 'model/stl' }, { ok: true, type: ' Text/HTML; charset=utf-8' }]) {
    let cancelled = 0;
    const parent = new AbortController();
    current = { ok: details.ok, headers: new Headers({ 'Content-Type': details.type }), bodyUsed: false,
      body: { cancel: async () => { ++cancelled; }, getReader: () => assert.fail('Unread body consumed') } };
    await assert.rejects(readOriginal(url, parent.signal), /could not be loaded/);
    assert.equal(cancelled, 1);
    context.mock.timers.tick(ORIGINAL_IDLE_MS * 2);
    assert.equal(parent.signal.aborted, false);
  }
  current = new Response(new Uint8Array(MAX_FILE_BYTES + 1));
  await assert.rejects(readOriginal(url, new AbortController().signal), /8 MiB/);
  current = new Response(new Uint8Array(0));
  await assert.rejects(readOriginal(url, new AbortController().signal), /empty/);
});
