export const DRAFT_KEY = 'everyday-prints-draft';
export const MAX_DRAFT_BYTES = 16 * 1024;

export function loadDraft(id, item) {
  try {
    const text = sessionStorage.getItem(DRAFT_KEY);
    if (!text || new TextEncoder().encode(text).byteLength > MAX_DRAFT_BYTES) return null;
    const draft = JSON.parse(text);
    if (!draft || draft.id !== id || draft.model !== item.name ||
        !draft.values || typeof draft.values !== 'object' || Array.isArray(draft.values) ||
        Object.keys(draft.values).length !== item.parameters.length ||
        item.parameters.some(field => !Object.hasOwn(draft.values, field.key) || typeof draft.values[field.key] !== 'string')) return null;
    return { model: draft.model, values: draft.values, recovered: true };
  } catch { return null; }
}

export function saveDraft(id, item, values) {
  try {
    const text = JSON.stringify({ id, model: item.name, values });
    if (new TextEncoder().encode(text).byteLength > MAX_DRAFT_BYTES) {
      sessionStorage.removeItem(DRAFT_KEY);
      return false;
    }
    sessionStorage.setItem(DRAFT_KEY, text);
    return true;
  } catch {
    // Do not recover an older snapshot after the latest write failed.
    try { sessionStorage.removeItem(DRAFT_KEY); } catch { /* Storage can be disabled. */ }
    return false;
  }
}
