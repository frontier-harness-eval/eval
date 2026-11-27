// Stores an API key on one model entry of a PenguinHarness data root without the key ever
// appearing on a command line or in the environment: the key is read from a file inside this
// process and written with PenguinHarness core's addModel, the same upsert that
// `penguin config model add --api-key` performs. The entry's other fields (pricing, client
// type, base URL) are kept; add the model first if it does not exist yet, e.g.
// `PENGUIN_HOME=<data root> penguin config model add --provider deepseek --model-id deepseek-flash --set-default`.
//
//   PENGUIN_HOME=<data root> <node> agents/set_model_key.mjs <core index.js> <project> <provider> <model_id> <key file>
//
// <core index.js> is the installed PenguinHarness core:
//   - official installer: ~/.penguin/lib/node_modules/@prismshadow/penguin-core/dist/index.js,
//     run with the installer's Node.js, ~/.penguin/node/bin/node;
//   - npm install -g @prismshadow/penguin-cli:
//     $(npm root -g)/@prismshadow/penguin-cli/node_modules/@prismshadow/penguin-core/dist/index.js.
// <project> is usually default_project. Set PENGUIN_HOME on this one command (never export it):
// without it the default data root is used. The key file holds the key on one line and should
// be mode 0600. Prints one line naming the entry it stored, and no part of the key.
import fs from "node:fs";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
if (args.length !== 5) {
  process.stderr.write(
    "usage: PENGUIN_HOME=<data root> node agents/set_model_key.mjs <core index.js> <project> <provider> <model_id> <key file>\n",
  );
  process.exit(2);
}
const [coreIndex, projectId, provider, modelId, keyFile] = args;
if ((fs.statSync(keyFile).mode & 0o077) !== 0) {
  process.stderr.write(`warning: ${keyFile} is readable by other users; chmod 600 it\n`);
}
const { addModel, resolveRoot } = await import(pathToFileURL(coreIndex).href);
const key = fs.readFileSync(keyFile, "utf8").trim();
if (key.length < 8) throw new Error("the key file looks empty");
const root = resolveRoot();
await addModel(root, projectId, { provider, model_id: modelId, api_key: key });
process.stdout.write(`stored the api_key of (${provider}, ${modelId}) in ${root}/${projectId}\n`);
