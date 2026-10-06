import { bindings, defineConfig, defineContainer, exports } from "cf/config";
import * as entrypoint from "./src/index.ts" with { type: "cf-worker" };

const cad = defineContainer({
	name: "everyday-prints-cad",
	schedulingPolicy: "durable-object",
	observability: { enabled: true },
});

export default defineConfig({
	worker: {
		name: "everyday-prints",
		compatibilityDate: "2026-09-30",
		compatibilityFlags: ["nodejs_compat", "enable_ctx_exports"],
		entrypoint,
		assets: { notFoundHandling: "single-page-application", runWorkerFirst: ["/api/*"] },
		observability: { enabled: true },
		exports: { CadRuntime: exports.durableObject({ storage: "sqlite", container: cad }) },
		env: {
			ASSETS: bindings.assets(),
			BUILD_LIMIT: bindings.rateLimit({ namespace: "1001", simple: { limit: 12, period: 60 } }),
		},
	},
	containers: [cad],
});
