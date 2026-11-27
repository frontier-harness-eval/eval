import fs from "node:fs";
import path from "node:path";

const [root, project, agent] = process.argv.slice(2);
const endpoint = `/api/projects/${encodeURIComponent(project)}/agents/${encodeURIComponent(agent)}/config`;
const deadline = Date.now() + 60_000;
let status = "not_ready";
while (Date.now() < deadline) {
  try {
    const lock = JSON.parse(fs.readFileSync(path.join(root, "server.lock"), "utf8"));
    const token = fs.readFileSync(path.join(root, "api-token"), "utf8").trim();
    if (token && Number.isInteger(lock.port)) {
      const response = await fetch(`http://localhost:${lock.port}${endpoint}`, {
        headers: { authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(2500),
      });
      status = response.status;
      if (response.ok && (await response.json()).config) {
        console.log(JSON.stringify({ ready: true, status, model_requests: 0 }));
        process.exit(0);
      }
    }
  } catch {
    // Wait for the local server to create its lock, token and stock Agent.
  }
  await new Promise((resolve) => setTimeout(resolve, 700));
}
console.log(JSON.stringify({ ready: false, status, model_requests: 0 }));
process.exit(1);
