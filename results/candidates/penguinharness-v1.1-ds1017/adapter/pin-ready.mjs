import fs from "node:fs";
import path from "node:path";

const [root, project, agent] = process.argv.slice(2);
const endpoint = `/api/projects/${encodeURIComponent(project)}/agents/${encodeURIComponent(agent)}/config`;
let verification = { ready: false, model_requests: 0 };
const deadline = Date.now() + 60_000;
while (Date.now() < deadline) {
  try {
    const lock = JSON.parse(fs.readFileSync(path.join(root, "server.lock"), "utf8"));
    const token = fs.readFileSync(path.join(root, "api-token"), "utf8").trim();
    if (token && Number.isInteger(lock.port)) {
      const url = `http://localhost:${lock.port}${endpoint}`;
      const headers = { authorization: `Bearer ${token}` };
      const previous = await fetch(url, { headers, signal: AbortSignal.timeout(3_000) });
      if (previous.ok) {
        const oldConfig = (await previous.json()).config;
        const updated = await fetch(url, {
          method: "PUT",
          headers: { ...headers, "content-type": "application/json" },
          signal: AbortSignal.timeout(3_000),
          body: JSON.stringify({ config: { model: { thinkingLevel: "max" } } }),
        });
        verification = { ready: false, put_status: updated.status, model_requests: 0 };
        if (updated.ok) {
          const got = await fetch(url, { headers, signal: AbortSignal.timeout(3_000) });
          if (got.ok) {
            const nextConfig = (await got.json()).config;
            const level = nextConfig?.model?.thinkingLevel;
            if (typeof oldConfig.systemPrompt === "string" && oldConfig.systemPrompt === nextConfig.systemPrompt && level === "max") {
              console.log(JSON.stringify({ ...verification, ready: true, thinking_level: level, system_prompt_unchanged: true }));
              process.exit(0);
            }
          }
        }
      }
    }
  } catch (error) {
    verification = { ...verification, error_type: error.name, error_code: error.cause?.code ?? null };
  }
  await new Promise((resolve) => setTimeout(resolve, 800));
}
console.log(JSON.stringify(verification));
process.exit(1);

