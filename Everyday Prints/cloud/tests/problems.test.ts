import assert from 'node:assert/strict';
import test from 'node:test';
import { MAX_PROBLEM_BYTES, PROBLEM_WAIT_MS, responseProblem } from '../web/problems.js';

const fallback = 'The CAD download could not be built. Try again.';
const signal = () => new AbortController().signal;

test('short service errors retain their useful details and trim whitespace', async () => {
  for (const detail of ['Please wait a minute before building more models.', 'Clearance must be positive.', 'A'.repeat(512)]) {
    const response = Response.json({ error: `  ${detail}\n` }, { status: 503 });
    assert.equal(await responseProblem(response, signal(), fallback), detail);
    assert.equal(response.body.locked, false);
  }
});

test('malformed JSON and unexpected roots produce a usable retry message', async () => {
  for (const body of ['null', 'false', '4', '"Unavailable"', '[]', '{}', '{', '<html>Service unavailable</html>']) {
    const response = new Response(body, { status: 503 });
    assert.equal(await responseProblem(response, signal(), fallback), fallback);
    assert.equal(response.body.locked, false);
  }
});

test('empty, oversized, and non-string error fields cannot become diagnostics', async () => {
  for (const error of [null, false, 42, [], {}, '', ' \n ', 'A'.repeat(513)]) {
    const response = Response.json({ error }, { status: 500 });
    assert.equal(await responseProblem(response, signal(), fallback), fallback);
  }
});

test('error bodies stop at 16 KiB even when cancellation never settles', async () => {
  let reads = 0, cancelled = 0;
  const response = new Response(new ReadableStream({
    pull(controller) { reads++; controller.enqueue(new Uint8Array(MAX_PROBLEM_BYTES / 4)); },
    cancel() { cancelled++; return new Promise(() => {}); },
  }, { highWaterMark: 0 }), { status: 503, headers: { 'Content-Length': '1' } });
  assert.equal(await responseProblem(response, signal(), fallback), fallback);
  assert.equal(reads, 5);
  assert.equal(cancelled, 1);
  assert.equal(response.body.locked, false);
});

test('interrupted, empty, and missing error bodies retain retry guidance', async () => {
  let reads = 0;
  const interrupted = new Response(new ReadableStream({ pull(controller) {
    if (reads++ === 0) controller.enqueue(new TextEncoder().encode('{"error":'));
    else controller.error(new TypeError('Connection terminated'));
  } }, { highWaterMark: 0 }), { status: 503 });
  for (const response of [interrupted, new Response(null, { status: 503 }), new Response(new Uint8Array(), { status: 503 })]) {
    assert.equal(await responseProblem(response, signal(), fallback), fallback);
    assert.equal(response.body?.locked ?? false, false);
  }
});

test('split UTF-8 error details are decoded only after the complete body', async () => {
  const detail = 'Vérifiez les dimensions du modèle.';
  const bytes = new TextEncoder().encode(JSON.stringify({ error: detail }));
  const response = new Response(new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    controller.close();
  } }), { status: 400 });
  assert.equal(await responseProblem(response, signal(), fallback), detail);
  assert.equal(await responseProblem(new Response(new Uint8Array([123, 255, 125]), { status: 503 }), signal(), fallback), fallback);
});

test('stopping an error-body read cancels it and propagates the abort', async () => {
  const controller = new AbortController();
  let cancelled = 0;
  const response = new Response(new ReadableStream({ cancel() { cancelled++; } }), { status: 503 });
  const reading = responseProblem(response, controller.signal, fallback);
  controller.abort();
  await assert.rejects(reading, { name: 'AbortError' });
  assert.equal(cancelled, 1);
  assert.equal(response.body.locked, false);
});

test('late error bytes cannot replace a stopped request with a service failure', async () => {
  const controller = new AbortController();
  let release, cancelled = 0, released = 0;
  const response = { body: { getReader: () => ({
    read: () => new Promise(resolve => { release = resolve; }),
    cancel: async () => { cancelled++; },
    releaseLock: () => { released++; },
  }) } };
  const reading = responseProblem(response, controller.signal, fallback);
  controller.abort();
  await assert.rejects(reading, { name: 'AbortError' });
  assert.equal(cancelled, 1);
  assert.equal(released, 1);
  release({ done: false, value: new TextEncoder().encode('{"error":"Old service error"}') });
});

test('stalled error bodies cancel after five seconds and leave the request signal usable', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const controller = new AbortController();
  let cancelled = 0, settled = false;
  const response = new Response(new ReadableStream({ cancel() { cancelled++; } }), { status: 503 });
  const reading = responseProblem(response, controller.signal, fallback).then(value => { settled = true; return value; });
  context.mock.timers.tick(PROBLEM_WAIT_MS - 1);
  await Promise.resolve();
  assert.equal(settled, false);
  context.mock.timers.tick(1);
  assert.equal(await reading, fallback);
  assert.equal(cancelled, 1);
  assert.equal(response.body.locked, false);
  assert.equal(controller.signal.aborted, false);
  assert.equal(await responseProblem(Response.json({ error: 'Useful retry details.' }), controller.signal, fallback), 'Useful retry details.');
});

test('an error timeout releases an uncooperative reader before late bytes arrive', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  let release, cancelled = 0, released = 0;
  const response = { body: { getReader: () => ({
    read: () => new Promise(resolve => { release = resolve; }),
    cancel: async () => { cancelled++; },
    releaseLock: () => { released++; },
  }) } };
  const reading = responseProblem(response, signal(), fallback);
  context.mock.timers.tick(PROBLEM_WAIT_MS);
  assert.equal(await reading, fallback);
  assert.equal(cancelled, 1);
  assert.equal(released, 1);
  release({ done: false, value: new TextEncoder().encode('{"error":"Too late"}') });
  await Promise.resolve();
  assert.equal(released, 1);
});
