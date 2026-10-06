import assert from 'node:assert/strict';
import test from 'node:test';
import { MAX_FILE_BYTES, readFile } from '../web/transfer.js';

test('binary chunks retain their exact order without trusting Content-Length', async () => {
  const body = new ReadableStream({ start(controller) {
    controller.enqueue(new Uint8Array([0, 255]));
    controller.enqueue(new Uint8Array([127, 2]));
    controller.close();
  } });
  const response = new Response(body, { headers: { 'Content-Length': '999999999' } });
  assert.deepEqual(new Uint8Array(await readFile(response, new AbortController().signal)), new Uint8Array([0, 255, 127, 2]));
  assert.equal(response.body.locked, false);
});

test('a file at the exact 8 MiB boundary is accepted', async () => {
  const response = new Response(new Uint8Array(MAX_FILE_BYTES));
  const result = await readFile(response, new AbortController().signal);
  assert.equal(result.byteLength, MAX_FILE_BYTES);
  assert.equal(response.body.locked, false);
});

test('oversized streams stop before later chunks even when cancellation never settles', async () => {
  let reads = 0, cancelled = 0;
  const response = new Response(new ReadableStream({
    pull(controller) { reads++; controller.enqueue(new Uint8Array(MAX_FILE_BYTES / 4)); },
    cancel() { cancelled++; return new Promise(() => {}); },
  }, { highWaterMark: 0 }));
  await assert.rejects(readFile(response, new AbortController().signal), /8 MiB download limit/);
  assert.equal(reads, 5);
  assert.equal(cancelled, 1);
  assert.equal(response.body.locked, false);
});

test('interrupted streams report a retryable transfer error and release their reader', async () => {
  let reads = 0;
  const response = new Response(new ReadableStream({ pull(controller) {
    if (reads++ === 0) controller.enqueue(new Uint8Array([1, 2]));
    else controller.error(new TypeError('Connection terminated'));
  } }, { highWaterMark: 0 }));
  await assert.rejects(readFile(response, new AbortController().signal), /transfer was interrupted/);
  assert.equal(response.body.locked, false);
});

test('an already stopped request never begins reading', async () => {
  const controller = new AbortController();
  controller.abort();
  const response = new Response(new Uint8Array([1]));
  await assert.rejects(readFile(response, controller.signal), { name: 'AbortError' });
  assert.equal(response.bodyUsed, false);
});

test('stopping a pending read cancels its stream and releases the reader', async () => {
  const controller = new AbortController();
  let cancelled = 0;
  const response = new Response(new ReadableStream({ cancel() { cancelled++; } }));
  const reading = readFile(response, controller.signal);
  controller.abort();
  await assert.rejects(reading, { name: 'AbortError' });
  assert.equal(cancelled, 1);
  assert.equal(response.body.locked, false);
});

test('empty and missing bodies cannot become downloads', async () => {
  for (const response of [new Response(null), new Response(new Uint8Array())]) {
    await assert.rejects(readFile(response, new AbortController().signal), /transfer was empty/);
    assert.equal(response.body?.locked ?? false, false);
  }
});

test('late bytes from an uncooperative reader remain stopped', async () => {
  const controller = new AbortController();
  let release, cancelled = 0, released = 0;
  const response = { body: { getReader: () => ({
    read: () => new Promise(resolve => { release = resolve; }),
    cancel: async () => { cancelled++; },
    releaseLock: () => { released++; },
  }) } };
  const reading = readFile(response, controller.signal);
  controller.abort();
  await assert.rejects(reading, { name: 'AbortError' });
  assert.equal(cancelled, 1);
  assert.equal(released, 1);
  release({ done: false, value: new Uint8Array([1, 2, 3]) });
});

test('progress counts received bytes without trusting the response size', async () => {
  const progress: number[] = [];
  const chunks = [new Uint8Array([1, 2]), new Uint8Array([3])];
  const response = new Response(new ReadableStream({
    pull(controller) {
      if (chunks.length) controller.enqueue(chunks.shift());
      else controller.close();
    },
  }), { headers: { 'Content-Length': '1' } });
  const buffer = await readFile(response, new AbortController().signal, undefined, bytes => progress.push(bytes));
  assert.deepEqual(progress, [2, 3]);
  assert.deepEqual(new Uint8Array(buffer), new Uint8Array([1, 2, 3]));
});

test('progress stops at the size limit before an oversized chunk is reported', async () => {
  const progress: number[] = [];
  let cancelled = 0;
  const response = new Response(new ReadableStream({
    pull(controller) { controller.enqueue(new Uint8Array(2)); },
    cancel() { cancelled++; },
  }), { headers: { 'Content-Length': '1' } });
  await assert.rejects(readFile(response, new AbortController().signal, 3, bytes => progress.push(bytes)), /size limit/);
  assert.deepEqual(progress, [2]);
  assert.equal(cancelled, 1);
  assert.equal(response.body.locked, false);
});

test('late bytes cannot report progress after Stop releases a pending reader', async () => {
  const controller = new AbortController();
  const progress: number[] = [];
  let releaseTail, startTail, reads = 0, cancelled = 0, released = 0;
  const waiting = new Promise(resolve => { startTail = resolve; });
  const response = { body: { getReader: () => ({
    read: async () => {
      if (reads++ === 0) return { done: false, value: new Uint8Array([1, 2]) };
      return new Promise(resolve => { releaseTail = resolve; startTail(); });
    },
    cancel: async () => { cancelled++; },
    releaseLock: () => { released++; },
  }) } };
  const reading = readFile(response, controller.signal, undefined, bytes => progress.push(bytes));
  await waiting;
  controller.abort();
  await assert.rejects(reading, { name: 'AbortError' });
  releaseTail({ done: false, value: new Uint8Array([3]) });
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(progress, [2]);
  assert.equal(cancelled, 1);
  assert.equal(released, 1);
});

test('reusing a chunk buffer cannot change bytes already received', async () => {
  const chunk = new Uint8Array(2);
  let index = 0;
  const response = new Response(new ReadableStream({
    pull(controller) {
      if (index === 2) { controller.close(); return; }
      chunk.set(index++ === 0 ? [1, 2] : [3, 4]);
      controller.enqueue(chunk);
    },
  }, { highWaterMark: 0 }));
  const data = await readFile(response, new AbortController().signal);
  assert.deepEqual(new Uint8Array(data), new Uint8Array([1, 2, 3, 4]));
  chunk.fill(255);
  assert.deepEqual(new Uint8Array(data), new Uint8Array([1, 2, 3, 4]));
});

test('fragmented borrowed views produce exactly the file bytes at an odd limit', async () => {
  const backing = new Uint8Array(1024 * 1024);
  const chunk = backing.subarray(backing.length - 1);
  let index = 0;
  const response = new Response(new ReadableStream({
    pull(controller) {
      if (index === 13) { controller.close(); return; }
      chunk[0] = index++;
      controller.enqueue(chunk);
    },
  }, { highWaterMark: 0 }));
  const data = await readFile(response, new AbortController().signal, 13);
  assert.equal(data.byteLength, 13);
  assert.deepEqual(new Uint8Array(data), new Uint8Array(Array.from({ length: 13 }, (_, value) => value)));
  backing.fill(255);
  assert.equal(new Uint8Array(data)[12], 12);
});

test('empty chunks neither report bytes nor displace valid data', async () => {
  const progress: number[] = [];
  const chunks = [new Uint8Array(), new Uint8Array([8]), new Uint8Array(), new Uint8Array([9, 10]), new Uint8Array()];
  const response = new Response(new ReadableStream({
    pull(controller) {
      if (chunks.length) controller.enqueue(chunks.shift());
      else controller.close();
    },
  }, { highWaterMark: 0 }));
  const data = await readFile(response, new AbortController().signal, 3, bytes => progress.push(bytes));
  assert.deepEqual(new Uint8Array(data), new Uint8Array([8, 9, 10]));
  assert.deepEqual(progress, [1, 3]);
  const empty = new Response(new ReadableStream({ start(controller) {
    controller.enqueue(new Uint8Array());
    controller.enqueue(new Uint8Array());
    controller.close();
  } }));
  await assert.rejects(readFile(empty, new AbortController().signal), /transfer was empty/);
});
