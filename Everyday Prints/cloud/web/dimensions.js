export const MAX_DIMENSIONS_BYTES = 16384;

export function parameterError(field, text) {
  return Object.assign(new Error(`${field.label}: ${text}`), { parameter: field.key });
}

export function dimensionParameters(item, overrides) {
  if (!overrides || typeof overrides !== 'object' || Array.isArray(overrides)) throw new Error('Dimensions need a parameters object.');
  const parameters = structuredClone(item.defaults);
  for (const [key, value] of Object.entries(overrides)) {
    const field = item.parameters.find(field => field.key === key);
    if (!field) throw new Error(`Unknown parameter: ${key.length > 80 ? key.slice(0, 80) + '…' : key}.`);
    if (field.type === 'list') {
      if (!Array.isArray(value) || !value.length || value.length > 16) throw parameterError(field, 'use 1 to 16 numbers.');
    } else if (Array.isArray(value)) throw parameterError(field, 'use one number.');
    const values = field.type === 'list' ? value : [value];
    if (values.some(number => typeof number !== 'number' || !Number.isFinite(number) || Math.abs(number) > 1000)) throw parameterError(field, 'use numbers between -1000 and 1000.');
    if (field.type === 'integer' && !Number.isInteger(value)) throw parameterError(field, 'use a whole number.');
    if (values.some(number => number < (field.min ?? -1000) || number > (field.max ?? 1000))) {
      const range = field.min !== undefined && field.max !== undefined ? `between ${field.min} and ${field.max}` : field.min !== undefined ? `at least ${field.min}` : `at most ${field.max}`;
      throw parameterError(field, `use a number ${range}.`);
    }
    parameters[key] = Array.isArray(value) ? [...value] : value;
  }
  return parameters;
}

export function dimensionRecord(item, overrides) {
  const parameters = dimensionParameters(item, overrides);
  return { model: item.name, parameters, units: 'mm', ...(item.kind === 'assembly' ? { kit: structuredClone(item.kit) } : {}) };
}

export function savedDimensions(text, models) {
  if (new TextEncoder().encode(text).byteLength > MAX_DIMENSIONS_BYTES) throw new Error('The saved dimensions file exceeds 16 KiB. Choose a parameters.json file.');
  let record;
  try { record = JSON.parse(text.replace(/^\uFEFF/, '')); }
  catch { throw new Error('This file is not valid JSON. Choose a saved dimensions or parameters.json file.'); }
  if (!record || typeof record !== 'object' || Array.isArray(record)) throw new Error('Choose a saved dimensions or parameters.json file.');
  if (record.units !== 'mm') throw new Error('Saved dimensions must use millimeters (units: mm).');
  const item = models.find(model => model.name === record.model);
  if (!item) throw new Error('This saved model is not in the library.');
  return { item, parameters: dimensionRecord(item, record.parameters).parameters };
}
