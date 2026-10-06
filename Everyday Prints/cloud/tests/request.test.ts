import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { bodyWithinLimit, MAX_BODY, validate } from "../src/request.ts";

const { manifest } = JSON.parse(readFileSync(new URL("../src/generated/runtime.json", import.meta.url), "utf8"));
const { models } = JSON.parse(readFileSync(new URL("../public/catalog.json", import.meta.url), "utf8"));
const payload = (parameters: unknown, model = "parts_tray") => JSON.stringify({ model, parameters });

test("all catalog defaults and parameter types agree with the runtime manifest", () => {
	assert.equal(models.length, Object.keys(manifest).length);
	for (const model of models) {
		assert.deepEqual(JSON.parse(validate(JSON.stringify({ model: model.name }), manifest)).parameters, model.defaults);
		assert.deepEqual(manifest[model.name].integer_parameters,
			model.parameters.filter((field: { type: string }) => field.type === "integer").map((field: { key: string }) => field.key));
		for (const key of manifest[model.name].integer_parameters) {
			assert.throws(() => validate(payload({ [key]: model.defaults[key] + .5 }, model.name), manifest), /integer/);
		}
	}
});

test("continuous dimensions retain fractional overrides even when defaults are whole", () => {
	assert.equal(JSON.parse(validate(payload({ length: 180.5 }), manifest)).parameters.length, 180.5);
});

test("CAD exports use the same validated parameters and reject unsupported formats", () => {
	for (const format of ["cad", "stl"]) {
		const value = JSON.parse(validate(JSON.stringify({ model: "parts_tray", parameters: { length: 180.5 }, format }), manifest));
		assert.equal(value.format, format);
		assert.equal(value.parameters.length, 180.5);
	}
	assert.equal(JSON.parse(validate(payload({}), manifest)).format, undefined);
	for (const format of [null, "step", "3mf", "../../evil", 1, {}, []]) {
		assert.throws(() => validate(JSON.stringify({ model: "parts_tray", format }), manifest), /format/);
	}
});

test("null, arrays, and scalars cannot substitute for a parameters object", () => {
	for (const value of [null, [], "180", 180, true]) {
		assert.throws(() => validate(payload(value), manifest), /Parameters must be an object/);
	}
});

test("unknown models, prototype names, and unexpected keys are rejected", () => {
	for (const model of ["../../evil", "toString", "constructor", "__proto__"]) {
		assert.throws(() => validate(payload({}, model), manifest), /Unknown model/);
	}
	for (const key of ["unknown", "constructor", "__proto__"]) {
		assert.throws(() => validate(payload({ [key]: 1 }), manifest), /Unknown parameter/);
	}
	assert.throws(() => validate('{"model":"parts_tray","extra":1}', manifest), /Expected/);
	for (const body of ["null", "[]", "true", "1", '"parts_tray"']) {
		assert.throws(() => validate(body, manifest));
	}
});

test("numeric strings, booleans, array mismatches, and out-of-bounds values are rejected", () => {
	for (const length of ["180", true, null, [180], 1001, -1001, Infinity]) {
		assert.throws(() => validate(payload({ length }), manifest));
	}
	for (const cable_diameters of [[], Array(17).fill(2), [true], ["2"], [null], 2]) {
		assert.throws(() => validate(payload({ cable_diameters }, "cable_comb"), manifest));
	}
	assert.deepEqual(JSON.parse(validate(payload({ cable_diameters: [2, 3.5, 9] }, "cable_comb"), manifest)).parameters.cable_diameters, [2, 3.5, 9]);
});

test("reading limits actual bytes without relying on Content-Length", async () => {
	const text = "x".repeat(MAX_BODY);
	assert.equal(await bodyWithinLimit(new Request("http://cad/generate", { method: "POST", body: text })), text);
	await assert.rejects(bodyWithinLimit(new Request("http://cad/generate", { method: "POST", body: text + "x" })), /too large/);
	await assert.rejects(bodyWithinLimit(new Request("http://cad/generate", { method: "POST", body: "é".repeat(MAX_BODY) })), /too large/);
	await assert.rejects(bodyWithinLimit(new Request("http://cad/generate", { method: "POST" })), /required/);
});

test("oversized streamed bodies are cancelled before consuming later chunks", async () => {
	let reads = 0, cancelled = false;
	const body = new ReadableStream({
		pull(controller) { reads++; controller.enqueue(new Uint8Array(MAX_BODY)); },
		cancel() { cancelled = true; },
	}, { highWaterMark: 0 });
	// Node requires duplex for streaming requests; Workers do not.
	const request = new Request("http://cad/generate", { method: "POST", body, duplex: "half" });
	await assert.rejects(bodyWithinLimit(request), /too large/);
	assert.equal(cancelled, true);
	assert.equal(reads, 2);
});

test("UTF-8 split across chunks remains intact", async () => {
	const bytes = new TextEncoder().encode("{\"name\":\"é\"}");
	const body = new ReadableStream({ start(controller) {
		for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
		controller.close();
	} });
	const request = new Request("http://cad/generate", { method: "POST", body, duplex: "half" });
	assert.equal(await bodyWithinLimit(request), '{"name":"é"}');
});
