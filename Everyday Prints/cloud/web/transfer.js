export const MAX_FILE_BYTES = 8 * 1024 * 1024;

function readChunk(reader, signal) {
  return new Promise((resolve, reject) => {
    const clear = () => signal.removeEventListener('abort', stop);
    const stop = () => { clear(); reject(signal.reason); };
    signal.addEventListener('abort', stop, { once: true });
    if (signal.aborted) { stop(); return; }
    try {
      reader.read().then(
        chunk => { clear(); resolve(chunk); },
        error => { clear(); reject(error); }
      );
    } catch (error) { clear(); reject(error); }
  });
}

export async function readFile(response, signal, maxBytes = MAX_FILE_BYTES, onProgress) {
  signal.throwIfAborted();
  const reader = response.body?.getReader();
  if (!reader) throw new Error('The file transfer was empty. Try again.');
  const cancel = () => { reader.cancel().catch(() => {}); };
  signal.addEventListener('abort', cancel, { once: true });
  let data = new Uint8Array(0);
  let bytes = 0;
  try {
    if (signal.aborted) { cancel(); signal.throwIfAborted(); }
    for (;;) {
      let chunk;
      // A transport may ignore cancellation; the caller must still recover.
      try { chunk = await readChunk(reader, signal); }
      catch (error) {
        signal.throwIfAborted();
        if (error.name === 'AbortError') throw error;
        throw new Error('The file transfer was interrupted. Try again.');
      }
      signal.throwIfAborted();
      if (chunk.done) break;
      if (!chunk.value.byteLength) continue;
      const offset = bytes;
      bytes += chunk.value.byteLength;
      if (bytes > maxBytes) {
        cancel();
        throw new Error(maxBytes === MAX_FILE_BYTES ? 'This file exceeds the 8 MiB download limit. Try smaller dimensions or fewer repeated features.' : 'This response exceeds its size limit.');
      }
      if (bytes > data.byteLength) {
        const grown = new Uint8Array(Math.min(maxBytes, Math.max(bytes, data.byteLength * 2)));
        grown.set(data.subarray(0, offset));
        data = grown;
      }
      data.set(chunk.value, offset);
      onProgress?.(bytes);
    }
    if (!bytes) throw new Error('The file transfer was empty. Try again.');
    return bytes === data.byteLength ? data.buffer : data.slice(0, bytes).buffer;
  } finally {
    signal.removeEventListener('abort', cancel);
    reader.releaseLock();
  }
}
