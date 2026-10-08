import { MAX_FILE_BYTES, readFile } from './transfer.js';

export const ORIGINAL_IDLE_MS = 15000;

export async function readOriginal(url, parent, onProgress, reload = false) {
  const controller = new AbortController();
  const { signal } = controller;
  const stop = () => controller.abort(parent.reason);
  let timer, reject;
  const interrupted = new Promise((_, fail) => { reject = fail; });
  const aborted = () => reject(signal.reason);
  const active = () => {
    clearTimeout(timer);
    timer = setTimeout(() => controller.abort(new Error('The original preview stopped responding. Retry original preview or update the preview to try again.')), ORIGINAL_IDLE_MS);
  };
  const discard = response => { if (!response.bodyUsed) response.body?.cancel?.().catch(() => {}); };
  try {
    parent.throwIfAborted();
    parent.addEventListener('abort', stop, { once: true });
    signal.addEventListener('abort', aborted, { once: true });
    active();
    const pending = fetch(url, { signal, ...(reload ? { cache: 'reload' } : {}) }).then(response => {
      if (signal.aborted) { discard(response); throw signal.reason; }
      return response;
    });
    const response = await Promise.race([pending, interrupted]);
    if (signal.aborted) { discard(response); throw signal.reason; }
    if (!response.ok || response.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase() === 'text/html') {
      discard(response);
      throw new Error('The model preview could not be loaded.');
    }
    active();
    onProgress?.(0);
    return await readFile(response, signal, MAX_FILE_BYTES, bytes => { active(); onProgress?.(bytes); });
  } finally {
    clearTimeout(timer);
    parent.removeEventListener('abort', stop);
    signal.removeEventListener('abort', aborted);
  }
}
