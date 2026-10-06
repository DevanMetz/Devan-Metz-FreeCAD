import { readFile } from './transfer.js';

export const MAX_PROBLEM_BYTES = 16 * 1024;
export const PROBLEM_WAIT_MS = 5000;

export async function responseProblem(response, signal, fallback) {
  signal.throwIfAborted();
  const controller = new AbortController();
  const stop = () => controller.abort(signal.reason);
  signal.addEventListener('abort', stop, { once: true });
  const timer = setTimeout(() => controller.abort(), PROBLEM_WAIT_MS);
  try {
    if (signal.aborted) stop();
    const buffer = await readFile(response, controller.signal, MAX_PROBLEM_BYTES);
    const data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(buffer));
    const detail = typeof data?.error === 'string' ? data.error.trim() : '';
    return detail && detail.length <= 512 ? detail : fallback;
  } catch {
    signal.throwIfAborted();
    return fallback;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', stop);
  }
}
