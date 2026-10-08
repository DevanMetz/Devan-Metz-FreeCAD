import { MAX_DIMENSIONS_BYTES } from './dimensions.js';
import { MAX_FILE_BYTES, readWithSignal } from './transfer.js';

export const MAX_DIMENSIONS_ZIP_BYTES = MAX_FILE_BYTES;
export const isDimensionsZip = file => /\.zip$/i.test(file.name) || ['application/zip', 'application/x-zip-compressed'].includes(file.type);
const archiveError = text => Object.assign(new Error(text), { dimensionsFile: true });

export function checkDimensionsFile(file) {
  if (isDimensionsZip(file)) {
    if (file.size > MAX_DIMENSIONS_ZIP_BYTES) throw archiveError('The CAD ZIP exceeds 8 MiB. Extract its parameters.json file and choose that instead.');
  } else if (file.size > MAX_DIMENSIONS_BYTES) {
    throw new Error('The saved dimensions file exceeds 16 KiB. Choose a parameters.json file.');
  }
}

export async function readDimensionsFile(file, signal) {
  signal?.throwIfAborted();
  checkDimensionsFile(file);
  if (!isDimensionsZip(file)) return readWithSignal(() => file.text(), signal);
  let ZipReader, BlobReader;
  try { ({ ZipReader, BlobReader } = await readWithSignal(() => import('./zip.js'), signal)); }
  catch { signal?.throwIfAborted(); throw archiveError('ZIP reading is unavailable. Extract parameters.json from the ZIP and choose that file instead.'); }
  signal?.throwIfAborted();
  const blob = new BlobReader(file);
  const read = blob.readUint8Array.bind(blob);
  // ZIP directory reads use arrayBuffer(), which does not accept an AbortSignal.
  blob.readUint8Array = (offset, length) => readWithSignal(() => read(offset, length), signal);
  const reader = new ZipReader(blob, {
    strictness: 'strict', checkCrc32: true, useWebWorkers: false, signal,
  });
  try {
    let parameters, entries = 0, total = 0;
    for await (const entry of reader.getEntriesGenerator()) {
      signal?.throwIfAborted();
      if (++entries > 128) throw archiveError('The ZIP contains too many files. Choose a downloaded CAD or kit ZIP.');
      if (!Number.isSafeInteger(entry.uncompressedSize) || entry.uncompressedSize < 0) throw archiveError('The ZIP contains an invalid file size. Choose a downloaded CAD or kit ZIP.');
      total += entry.uncompressedSize;
      if (total > 24 * 1024 * 1024) throw archiveError('The ZIP contents exceed 24 MiB. Extract its parameters.json file and choose that instead.');
      if (entry.filename === 'parameters.json') {
        if (parameters || entry.directory) throw archiveError('Choose a CAD or kit ZIP with one parameters.json file at its top level.');
        parameters = entry;
      }
    }
    if (!parameters) throw archiveError('The ZIP has no parameters.json file at its top level. Choose a downloaded CAD or kit ZIP.');
    if (parameters.encrypted) throw archiveError('Choose an unencrypted CAD or kit ZIP.');
    if (parameters.uncompressedSize > MAX_DIMENSIONS_BYTES) throw archiveError('The ZIP dimensions record exceeds 16 KiB. Choose a downloaded CAD or kit ZIP.');
    if (![0, 8].includes(parameters.compressionMethod)) throw archiveError('This ZIP compression is unsupported. Extract parameters.json and choose that file instead.');
    if (parameters.compressionMethod === 8 && typeof DecompressionStream === 'undefined') throw archiveError('ZIP reading is unavailable in this browser. Extract parameters.json and choose that file instead.');
    signal?.throwIfAborted();
    const chunks = [];
    let length = 0;
    await parameters.getData(new WritableStream({
      write(chunk) {
        if (length + chunk.byteLength > MAX_DIMENSIONS_BYTES) throw archiveError('The ZIP dimensions record exceeds 16 KiB. Choose a downloaded CAD or kit ZIP.');
        chunks.push(chunk.slice());
        length += chunk.byteLength;
      },
    }), { signal });
    if (length !== parameters.uncompressedSize) throw archiveError('The ZIP dimensions record is incomplete. Choose the ZIP again or extract parameters.json.');
    const bytes = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch (error) {
    if (signal?.aborted) throw signal.reason;
    if (error.dimensionsFile) throw error;
    throw archiveError('The CAD ZIP could not be verified. Choose an intact downloaded ZIP or its extracted parameters.json file.');
  } finally { await reader.close(); }
}
