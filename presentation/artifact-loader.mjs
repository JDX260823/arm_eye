const ARTIFACT_TOOL_URL = new URL(
  "file:///Users/silverbrick/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs",
);

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "@oai/artifact-tool") {
    return { url: ARTIFACT_TOOL_URL.href, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}
