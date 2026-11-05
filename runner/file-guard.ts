// pi extension loaded by run-task.sh; two rules for the file tools.
//
// 1. Every path stays inside the vault (the job's working folder). The sandbox lets
//    wikibot read every vault a runner serves and the other jobs' transcripts, so a
//    question in one wiki could otherwise read another wiki or someone else's chat.
//    Symlinks count by where they lead.
// 2. `write` may only create new files. Replacing a whole existing file drops whatever
//    the model didn't re-type (one ingest wiped wiki/log.md this way), so existing
//    files change only by `edit`.

import { existsSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const FILE_TOOLS = new Set(["read", "edit", "write", "grep", "find", "ls"]);

// Where a path really leads: the real path of its nearest existing folder, plus the rest.
function realTarget(path: string): string {
	let head = path;
	const rest: string[] = [];
	while (!existsSync(head) && dirname(head) !== head) {
		rest.unshift(head.slice(dirname(head).length + 1));
		head = dirname(head);
	}
	return resolve(realpathSync(head), ...rest);
}

export function outsideVault(path: string, vault: string): boolean {
	// pi strips a leading @ and expands ~ (the home folder is never inside a vault).
	const p = path.replace(/^@/, "");
	if (p === "~" || p.startsWith("~/")) return true;
	const rel = relative(realpathSync(vault), realTarget(resolve(vault, p)));
	return rel === ".." || rel.startsWith("../") || isAbsolute(rel);
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event) => {
		if (!FILE_TOOLS.has(event.toolName)) return undefined;
		const vault = process.cwd();
		const path = String(event.input.path ?? ".");
		if (outsideVault(path, vault)) {
			return { block: true, reason: `${path} is outside the wiki. Only paths inside it are allowed.` };
		}
		if (event.toolName === "write" && existsSync(resolve(vault, path.replace(/^@/, "")))) {
			return {
				block: true,
				reason: `${path} already exists. Don't rewrite it: read it and change it with edit.`,
			};
		}
		return undefined;
	});
}
