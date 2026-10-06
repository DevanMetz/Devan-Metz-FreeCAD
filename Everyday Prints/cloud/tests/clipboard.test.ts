import assert from 'node:assert/strict';
import test from 'node:test';
import { clipboardQueue } from '../web/clipboard.js';

test('clipboard writes finish in request order instead of racing', async () => {
  const pending = [], written = [];
  const copy = clipboardQueue(text => new Promise(resolve => pending.push(() => { written.push(text); resolve(); })));
  const first = copy('first'), last = copy('last');
  assert.equal(pending.length, 1);
  pending[0]();
  assert.equal(await first, true);
  assert.equal(pending.length, 2);
  pending[1]();
  assert.equal(await last, true);
  assert.deepEqual(written, ['first', 'last']);
});

test('only the latest queued request is retained', async () => {
  const pending = [], written = [];
  const copy = clipboardQueue(text => new Promise(resolve => pending.push(() => { written.push(text); resolve(); })));
  const first = copy('first'), superseded = copy('middle'), last = copy('last');
  assert.equal(await superseded, false);
  assert.equal(pending.length, 1);
  pending[0]();
  await first;
  pending[1]();
  await last;
  assert.deepEqual(written, ['first', 'last']);
});

test('a failed write does not prevent the latest queued copy', async () => {
  let rejectFirst;
  const written = [];
  const copy = clipboardQueue(text => {
    written.push(text);
    if (text === 'first') return new Promise((resolve, reject) => { rejectFirst = reject; });
  });
  const first = copy('first'), last = copy('last');
  const failed = assert.rejects(first, /denied/);
  rejectFirst(new Error('denied'));
  await failed;
  assert.equal(await last, true);
  assert.deepEqual(written, ['first', 'last']);
});

test('synchronous denial is retryable', async () => {
  let denied = true;
  const copy = clipboardQueue(() => { if (denied) throw new Error('denied'); });
  await assert.rejects(copy('first'), /denied/);
  denied = false;
  assert.equal(await copy('retry'), true);
});

test('a stalled write stores one latest request without starting additional writes', async () => {
  let writes = 0;
  const copy = clipboardQueue(() => { writes++; return new Promise(() => {}); });
  copy('first');
  let superseded = copy('queued-0');
  for (let index = 1; index <= 100; index++) {
    const latest = copy(`queued-${index}`);
    assert.equal(await superseded, false);
    superseded = latest;
  }
  assert.equal(writes, 1);
});
