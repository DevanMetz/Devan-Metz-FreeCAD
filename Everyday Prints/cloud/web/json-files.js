import { readWithSignal } from './transfer.js';

const jsonError = text => Object.assign(new Error(text), { jsonFile: true });

export async function readJsonFile(file, signal, maxBytes) {
  signal?.throwIfAborted();
  const tooLarge = () => jsonError(`The JSON file exceeds ${maxBytes / 1024} KiB. Choose a smaller saved file.`);
  if (file.size > maxBytes) throw tooLarge();
  const bytes = await readWithSignal(() => file.arrayBuffer(), signal);
  signal?.throwIfAborted();
  if (bytes.byteLength > maxBytes) throw tooLarge();
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
  catch { throw jsonError('This JSON file is not valid UTF-8. Save it as UTF-8 JSON and choose it again.'); }
}
