import { DurableObject } from "cloudflare:workers";
import runtime from "./generated/runtime.json";
import { bodyWithinLimit, validate, type ModelManifest } from "./request.ts";

const IDLE_MS = 5 * 60 * 1000;
const decoder = new TextDecoder();
const manifest = runtime.manifest satisfies ModelManifest;

function problem(message: string, status = 400, retry = false): Response {
	return Response.json({ error: message }, { status, headers: {
		"Cache-Control": "no-store",
		...(retry ? { "Retry-After": "5" } : {}),
	} });
}

export class CadRuntime extends DurableObject<Env> {
	private ready?: Promise<void>;
	private building = false;

	private async command(argv: string[], stdin?: string): Promise<void> {
		const container = this.ctx.container!;
		const started = Date.now();
		console.log(JSON.stringify({ event: "cad_setup_step", command: argv.slice(0, 3) }));
		const process = await container.exec(argv, stdin ? { stdin: new Response(stdin).body! } : undefined);
		const result = await process.output();
		if (result.exitCode !== 0) {
			console.error(JSON.stringify({ event: "cad_setup_failed", command: argv[0], code: result.exitCode,
				detail: decoder.decode(result.stderr).slice(-1800) }));
			throw new Error("CAD runtime setup failed.");
		}
		console.log(JSON.stringify({ event: "cad_setup_step_done", command: argv[0], milliseconds: Date.now() - started }));
	}

	private async boot(): Promise<void> {
		const container = this.ctx.container;
		if (!container) throw new Error("CAD container is unavailable.");
		const saved = await this.ctx.storage.get<{ version: string; snapshot: ContainerSnapshot; created: number }>("runtime");
		let restored = container.running;
		if (!restored && saved && Date.now() - saved.created < 27 * 86400000) {
			try {
				container.start({ containerSnapshot: saved.snapshot, entrypoint: ["sleep", "infinity"], enableInternet: false, instance: "standard-1" });
				await this.command(["node", "--version"]);
				restored = true;
			} catch {
				await container.destroy();
				await this.ctx.storage.delete("runtime");
			}
		}
		if (!restored) {
			console.log(JSON.stringify({ event: "cad_runtime_install", version: runtime.version }));
			container.start({ image: "cloudflare/debian-trixie", entrypoint: ["sleep", "infinity"], enableInternet: true, instance: "standard-1" });
			await container.setInactivityTimeout(IDLE_MS);
			await this.command(["timeout", "180", "apt-get", "update"]);
			await this.command(["timeout", "180", "apt-get", "install", "-y", "--no-install-recommends", "python3", "python3-venv", "libgl1", "libglib2.0-0t64", "libxrender1", "libxext6"]);
			await this.command(["python3", "-m", "venv", "/opt/cad"]);
			await this.command(["timeout", "300", "/opt/cad/bin/pip", "install", "--no-cache-dir", "build123d==0.11.1", "cadgen==0.4.4"]);
		}
		await container.setInactivityTimeout(IDLE_MS);
		// Rewrite sources after every cold start. The snapshot supplies dependencies,
		// while the deployed bundle always supplies the authoritative model versions.
		const writeFiles = "const fs=require('node:fs');let s='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>{fs.mkdirSync('/app',{recursive:true});for(const [name,body] of Object.entries(JSON.parse(s)))fs.writeFileSync('/app/'+name,body);});";
		await this.command(["node", "-e", writeFiles], JSON.stringify({ ...runtime.files, "version.txt": runtime.version }));
		await this.command(["/opt/cad/bin/python", "-c", "import build123d; import cadgen.assembly; print('CAD ready')"]);
		if (!restored || saved?.version !== runtime.version) {
			const snapshot = await container.snapshotContainer({ name: `everyday-prints-${runtime.version}` });
			await this.ctx.storage.put("runtime", { version: runtime.version, snapshot, created: Date.now() });
			if (!restored) {
				// Ordinary jobs restore this filesystem without Internet access.
				await container.destroy();
				container.start({ containerSnapshot: snapshot, entrypoint: ["sleep", "infinity"], enableInternet: false, instance: "standard-1" });
				await this.command(["node", "--version"]);
				await this.command(["node", "-e", writeFiles], JSON.stringify({ ...runtime.files, "version.txt": runtime.version }));
			}
		}
		await container.setInactivityTimeout(IDLE_MS);
	}

	async fetch(request: Request): Promise<Response> {
		if (this.building) return problem("The CAD builder is busy. Try again shortly.", 503, true);
		this.building = true;
		try {
			if (!this.ctx.container?.running) this.ready = undefined;
			this.ready ??= this.boot();
			await this.ready;
			await this.ctx.container!.setInactivityTimeout(IDLE_MS);
			const payload = await bodyWithinLimit(request);
			const process = await this.ctx.container!.exec(["timeout", "90", "/opt/cad/bin/python", "/app/run_job.py"], { stdin: new Response(payload).body! });
			const output = await process.output();
			if (output.exitCode === 124) return problem("This build exceeded 90 seconds. Reduce repeated features or simplify the parameters.", 422);
			const text = decoder.decode(output.stdout).trim().split("\n").at(-1) ?? "";
			let result: { error?: string; file: string; metadata: { model: string; printable: boolean; format: string } };
			try { result = JSON.parse(text); }
			catch {
				console.error(JSON.stringify({ event: "cad_job_failed", code: output.exitCode, stderr: decoder.decode(output.stderr).slice(-1000) }));
				return problem("The CAD builder could not finish this model. Try again.", 503, true);
			}
			if (output.exitCode !== 0 || result.error) return problem(result.error ?? "These parameters could not be built.", 422);
			const cad = result.metadata.format === "cad";
			const bytes = Uint8Array.from(atob(result.file), character => character.charCodeAt(0));
			return new Response(bytes, { headers: {
				"Content-Type": cad ? "application/zip" : "model/stl", "Cache-Control": "no-store",
				"Content-Disposition": `attachment; filename="${result.metadata.model}-custom.${cad ? "zip" : "stl"}"`,
				"X-Model-Metadata": encodeURIComponent(JSON.stringify(result.metadata)),
			} });
		} catch (error) {
			this.ready = undefined;
			console.error(JSON.stringify({ event: "cad_request_failed", error: String(error) }));
			return problem("The CAD service could not start. Try again shortly.", 503, true);
		} finally { this.building = false; }
	}
}

export default {
	async fetch(request, env, ctx): Promise<Response> {
		const url = new URL(request.url);
		if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
		if (url.pathname === "/api/health" && request.method === "GET") return Response.json({ ok: true, version: runtime.version, models: Object.keys(manifest).length });
		if (url.pathname !== "/api/generate") return problem("Not found.", 404);
		if (request.method !== "POST") return problem("Use POST to customize a model.", 405);
		const origin = request.headers.get("Origin");
		if (origin && origin !== url.origin) return problem("Use the parameter editor on this site.", 403);
		if (!request.headers.get("Content-Type")?.startsWith("application/json")) return problem("Send parameters as JSON.", 415);
		let body: string;
		try { body = validate(await bodyWithinLimit(request), manifest); }
		catch (error) { return problem(error instanceof SyntaxError ? "Invalid JSON." : (error as Error).message); }
		const ip = request.headers.get("CF-Connecting-IP") ?? "local";
		const limit = await env.BUILD_LIMIT.limit({ key: ip });
		if (!limit.success) return problem("Please wait a minute before building more models.", 429, true);
		const stub = ctx.exports.CadRuntime.getByName("cad-runtime-v1");
		const result = await stub.fetch("http://cad/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body });
		const headers = new Headers(result.headers);
		headers.set("Cache-Control", "no-store");
		headers.set("X-Content-Type-Options", "nosniff");
		return new Response(result.body, { status: result.status, headers });
	},
} satisfies ExportedHandler<Env>;
