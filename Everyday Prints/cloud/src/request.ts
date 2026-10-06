export type ModelManifest = Record<string, {
	defaults: Record<string, number | number[]>;
	integer_parameters: string[];
	kind: string;
}>;

export const MAX_BODY = 16384;

export async function bodyWithinLimit(request: Request): Promise<string> {
	if (!request.body) throw new Error("A parameters request is required.");
	const reader = request.body.getReader();
	let total = 0;
	const chunks: Uint8Array[] = [];
	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		total += value.byteLength;
		if (total > MAX_BODY) {
			await reader.cancel();
			throw new Error("Parameter request is too large.");
		}
		chunks.push(value);
	}
	const bytes = new Uint8Array(total);
	let offset = 0;
	for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
	return new TextDecoder().decode(bytes);
}

export function validate(body: string, manifest: ModelManifest): string {
	const payload = JSON.parse(body) as { model?: unknown; parameters?: unknown; format?: unknown };
	if (!payload || typeof payload !== "object" || Array.isArray(payload) ||
		Object.keys(payload).some(key => !["model", "parameters", "format"].includes(key))) throw new Error("Expected a model and parameters.");
	if (payload.format !== undefined && payload.format !== "stl" && payload.format !== "cad") throw new Error("Choose STL or CAD format.");
	if (typeof payload.model !== "string" || !Object.hasOwn(manifest, payload.model)) throw new Error("Unknown model.");
	const model = manifest[payload.model];
	const overrides = payload.parameters === undefined ? {} : payload.parameters;
	if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) throw new Error("Parameters must be an object.");
	const parameters: Record<string, number | number[]> = { ...model.defaults };
	for (const [key, value] of Object.entries(overrides)) {
		if (!Object.hasOwn(model.defaults, key)) throw new Error(`Unknown parameter: ${key}.`);
		const sequence = Array.isArray(model.defaults[key]);
		if (sequence && (!Array.isArray(value) || value.length < 1 || value.length > 16)) throw new Error(`${key} needs 1 to 16 numbers.`);
		if (!sequence && Array.isArray(value)) throw new Error(`${key} needs one number.`);
		const values = sequence ? value as unknown[] : [value];
		if (values.some(v => typeof v !== "number" || !Number.isFinite(v) || Math.abs(v) > 1000)) throw new Error(`${key} needs finite numbers between -1000 and 1000.`);
		// JSON loses the distinction between Python's 150.0 dimension and int counts.
		if (model.integer_parameters.includes(key) && !Number.isInteger(value)) throw new Error(`${key} must be an integer.`);
		parameters[key] = value as number | number[];
	}
	return JSON.stringify({ model: payload.model, parameters, ...(payload.format !== undefined ? { format: payload.format } : {}) });
}
