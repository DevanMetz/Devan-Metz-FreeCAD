export const PRINTER_STORAGE = 'everydayPrints.printerVolume';

export function validPrinterVolume(volume) {
  return Array.isArray(volume) && volume.length === 3 && volume.every(value => typeof value === 'number' && Number.isFinite(value) && value > 0);
}

export function readPrinterVolume(storage) {
  const raw = storage.getItem(PRINTER_STORAGE);
  if (raw === null) return null;
  let volume;
  try {
    if (typeof raw !== 'string' || raw.length > 256) throw new Error();
    volume = JSON.parse(raw);
    if (!validPrinterVolume(volume)) throw new Error();
  } catch {
    throw new Error('Saved printer settings could not be read. Current build volume is kept.');
  }
  return volume;
}
