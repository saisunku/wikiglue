// pi extension loaded by run-task.sh: `write` may only create new files.
// Replacing a whole existing file drops whatever the model didn't re-type
// (one ingest wiped wiki/log.md this way), so existing files change only by `edit`.

import { existsSync } from "node:fs";
import { resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event) => {
		if (event.toolName !== "write") return undefined;
		const path = String(event.input.path ?? "").replace(/^@/, "");
		if (!existsSync(resolve(process.cwd(), path))) return undefined;
		return {
			block: true,
			reason: `${path} already exists. Don't rewrite it: read it and change it with edit.`,
		};
	});
}
